# -*- coding: Latin-1 -*-
#
# Linux OOMAnalyser
#
# Copyright (c) 2017-2023 Carsten Grohmann
# License: MIT (see LICENSE.txt)
# THIS PROGRAM COMES WITH NO WARRANTY
import math
import re

DEBUG = False
"""Show additional information during the development cycle"""

VERSION = "0.6.0 (devel)"
"""Version number"""

# __pragma__ ('skip')
# MOC objects to satisfy statical checker and imports in unit tests
js_undefined = 0


class classList:
    def add(self, *args, **kwargs):
        pass

    def remove(self, *args, **kwargs):
        pass

    def toggle(self, *args, **kwargs):
        pass


class document:
    def querySelectorAll(
        self,
        *args,
    ):
        return [Node()]

    @staticmethod
    def getElementsByClassName(names):
        """
        Returns an array-like object of all child elements which have all the given class name(s).

        @param names: A string representing the class name(s) to match; multiple class names are separated by whitespace.
        @type names: List(str)
        @rtype: List(Node)
        """
        return [Node()]

    @staticmethod
    def getElementById(_id):
        """
        Returns an object representing the element whose id property matches

        @type _id: str
        @rtype: Node
        """
        return Node()

    @staticmethod
    def createElementNS(namespaceURI, qualifiedName, *arg):
        """
        Creates an element with the specified namespace URI and qualified name.

        @param str namespaceURI:  Namespace URI to associate with the element
        @param str qualifiedName: Type of element to be created
        @rtype: Node
        """
        return Node()

    @staticmethod
    def createElement(tagName, *args):
        """
        Creates the HTML element specified by tagName.

        @param str tagName: Type of element to be created
        @rtype: Node
        """
        return Node()


class Node:
    classList = classList()
    id = None
    offsetWidth = 0
    textContent = ""

    def __init__(self, nr_children=1):
        self.nr_children = nr_children

    @property
    def firstChild(self):
        if self.nr_children:
            self.nr_children -= 1
            return Node(self.nr_children)
        else:
            return None

    def removeChild(self, *args, **kwargs):
        return

    def appendChild(self, *args, **kwargs):
        return

    def setAttribute(self, *args, **kwargs):
        return

    @property
    def parentNode(self):
        return super().__new__(self)


# __pragma__ ('noskip')


class OOMEntityState:
    """Enum for completeness of the OOM block"""

    unknown = 0
    empty = 1
    invalid = 2
    started = 3
    complete = 4


class OOMEntityType:
    """Enum for the type of the OOM"""

    unknown = 0
    automatic = 1
    manual = 2


class OOMMemoryAllocFailureType:
    """Enum to store the results why the memory allocation could have failed"""

    not_started = 0
    """Analysis not started"""

    missing_data = 1
    """Missing data to start analysis"""

    failed_below_low_watermark = 2
    """Failed, because after satisfying this request, the free memory will be below the low memory watermark"""

    failed_no_free_chunks = 3
    """Failed, because no suitable chunk is free in the current or any higher order."""

    failed_unknown_reason = 4
    """Failed, but the reason is unknown"""

    skipped_high_order_dont_trigger_oom = 5
    """"high order" requests don't trigger OOM"""


def is_visible(element):
    return element.offsetWidth > 0 and element.offsetHeight > 0


def hide_element(element_id):
    """Hide the given HTML element"""
    element = document.getElementById(element_id)
    element.classList.add("js-text--display-none")


def show_element(element_id):
    """Show the given HTML element"""
    element = document.getElementById(element_id)
    element.classList.remove("js-text--display-none")


def hide_elements(selector):
    """Hide all matching elements by adding class js-text--display-none"""
    for element in document.querySelectorAll(selector):
        element.classList.add("js-text--display-none")


def show_elements(selector):
    """Show all matching elements by removing class js-text--display-none"""
    for element in document.querySelectorAll(selector):
        element.classList.remove("js-text--display-none")


def toggle(element_id):
    """Toggle the visibility of the given HTML element"""
    element = document.getElementById(element_id)
    element.classList.toggle("js-text--display-none")


def escape_html(unsafe):
    """
    Escape unsafe HTML entities

    @type unsafe: str
    @rtype: str
    """
    return (
        unsafe.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def debug(msg):
    """Add debug message to the notification box"""
    add_to_notifybox("DEBUG", msg)


def error(msg):
    """Show the notification box and add the error message"""
    add_to_notifybox("ERROR", msg)


def internal_error(msg):
    """Show the notification box and add the internal error message"""
    add_to_notifybox("INTERNAL ERROR", msg)


def warning(msg):
    """Show the notification box and add the warning message"""
    add_to_notifybox("WARNING", msg)


def add_to_notifybox(prefix, msg):
    """
    Escaped and add message to the notification box

    If the message has a prefix "ERROR" or "WARNING" the notification box will be shown.
    """
    if prefix == "DEBUG":
        css_class = "js-notify_box__msg--debug"
    elif prefix == "WARNING":
        css_class = "js-notify_box__msg--warning"
    else:
        css_class = "js-notify_box__msg--error"
    if prefix != "DEBUG":
        show_element("notify_box")
    notify_box = document.getElementById("notify_box")
    notification = document.createElement("div")
    notification.classList.add(css_class)
    notification.innerHTML = "{}: {}<br>".format(prefix, escape_html(msg))
    notify_box.appendChild(notification)


class BaseKernelConfig:
    """Base class for all kernel specific configuration"""

    name = "Base configuration for all kernels based on vanilla kernel 3.10"
    """Name/description of this kernel configuration"""

    EXTRACT_PATTERN = None
    """
    Instance specific dictionary of RE pattern to analyse a OOM block for a specific kernel version

    This dict will be filled from EXTRACT_PATTERN_BASE and EXTRACT_PATTERN_OVERLAY during class constructor is executed.

    :type: None|Dict
    :see: EXTRACT_PATTERN_BASE and EXTRACT_PATTERN_OVERLAY
    """

    EXTRACT_PATTERN_BASE = {
        "invoked oom-killer": (
            r"^(?P<trigger_proc_name>[\S ]+) invoked oom-killer: "
            r"gfp_mask=(?P<trigger_proc_gfp_mask>0x[a-z0-9]+)(\((?P<trigger_proc_gfp_flags>[A-Z_|]+)\))?, "
            r"(nodemask=(?P<trigger_proc_nodemask>([\d,-]+|\(null\))), )?"
            r"order=(?P<trigger_proc_order>-?\d+), "
            r"oom_score_adj=(?P<trigger_proc_oomscore>\d+)",
            True,
        ),
        "Trigger process and kernel version": (
            r"^CPU: \d+ PID: (?P<trigger_proc_pid>\d+) "
            r"Comm: .* (Not tainted|Tainted:.*) "
            r"(?P<kernel_version>\d[\w.-]+) #\d",
            True,
        ),
        # split caused by a limited number of iterations during converting PY regex into JS regex
        # Source: mm/page_alloc.c:__show_free_areas()
        "Overall Mem-Info (part 1)": (
            r"^Mem-Info:.*" r"(?:\n)"
            # first line (starting w/o a space)
            r"^active_anon:(?P<active_anon_pages>\d+) inactive_anon:(?P<inactive_anon_pages>\d+) "
            r"isolated_anon:(?P<isolated_anon_pages>\d+)"
            r"(?:\n)"
            # remaining lines (w/ leading space)
            r"^ active_file:(?P<active_file_pages>\d+) inactive_file:(?P<inactive_file_pages>\d+) "
            r"isolated_file:(?P<isolated_file_pages>\d+)"
            r"(?:\n)"
            r"^ unevictable:(?P<unevictable_pages>\d+) dirty:(?P<dirty_pages>\d+) writeback:(?P<writeback_pages>\d+) "
            r"unstable:(?P<unstable_pages>\d+)",
            True,
        ),
        "Overall Mem-Info (part 2)": (
            r"^ slab_reclaimable:(?P<slab_reclaimable_pages>\d+) slab_unreclaimable:(?P<slab_unreclaimable_pages>\d+)"
            r"(?:\n)"
            r"^ mapped:(?P<mapped_pages>\d+) shmem:(?P<shmem_pages>\d+) pagetables:(?P<pagetables_pages>\d+) "
            r"bounce:(?P<bounce_pages>\d+)"
            r"(?:\n)"
            r"^ free:(?P<free_pages>\d+) free_pcp:(?P<free_pcp_pages>\d+) free_cma:(?P<free_cma_pages>\d+)",
            True,
        ),
        "Available memory chunks": (
            r"(?P<mem_node_info>(^Node \d+ ((DMA|DMA32|Normal):|(hugepages)).+(\n|$))+)",
            False,
        ),
        "Memory watermarks": (
            r"(?P<mem_watermarks>(^(Node \d+ (DMA|DMA32|Normal) free:|lowmem_reserve\[\]:).+(\n|$))+)",
            False,
        ),
        "Page cache": (
            r"^(?P<pagecache_total_pages>\d+) total pagecache pages.*$",
            True,
        ),
        # Source:mm/swap_state.c:show_swap_cache_info()
        "Swap usage information": (
            r"^(?P<swap_cache_pages>\d+) pages in swap cache"
            r"(?:\n)"
            r"^Swap cache stats: add \d+, delete \d+, find \d+\/\d+"
            r"(?:\n)"
            r"^Free swap  = (?P<swap_free_kb>\d+)kB"
            r"(?:\n)"
            r"^Total swap = (?P<swap_total_kb>\d+)kB",
            False,
        ),
        "Page information": (
            r"^(?P<ram_pages>\d+) pages RAM"
            r"("
            r"(?:\n)"
            r"^(?P<highmem_pages>\d+) pages HighMem/MovableOnly"
            r")?"
            r"(?:\n)"
            r"^(?P<reserved_pages>\d+) pages reserved"
            r"("
            r"(?:\n)"
            r"^(?P<cma_pages>\d+) pages cma reserved"
            r")?"
            r"("
            r"(?:\n)"
            r"^(?P<pagetablecache_pages>\d+) pages in pagetable cache"
            r")?"
            r"("
            r"(?:\n)"
            r"^(?P<hwpoisoned_pages>\d+) pages hwpoisoned"
            r")?",
            True,
        ),
        "Process killed by OOM": (
            r"^Out of memory: Kill process (?P<killed_proc_pid>\d+) \((?P<killed_proc_name>[\S ]+)\) "
            r"score (?P<killed_proc_score>\d+) or sacrifice child",
            True,
        ),
        "Details of process killed by OOM": (
            r"^Killed process \d+ \(.*\)"
            r"(, UID \d+,)?"
            r" total-vm:(?P<killed_proc_total_vm_kb>\d+)kB, anon-rss:(?P<killed_proc_anon_rss_kb>\d+)kB, "
            r"file-rss:(?P<killed_proc_file_rss_kb>\d+)kB, shmem-rss:(?P<killed_proc_shmem_rss_kb>\d+)kB.*",
            True,
        ),
    }
    """
    RE pattern to extract information from OOM.

    The first item is the RE pattern and the second is whether it is mandatory to find this pattern.

    This dictionary will be copied to EXTRACT_PATTERN during class constructor is executed.

    :type: dict(tuple(str, bool))
    :see: EXTRACT_PATTERN
    """

    EXTRACT_PATTERN_OVERLAY = {}
    """
    To extend / overwrite parts of EXTRACT_PATTERN in kernel configuration.

    :type: dict(tuple(str, bool))
    :see: EXTRACT_PATTERN
    """

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM"
        },
        "GFP_HIGHUSER_MOVABLE": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM | __GFP_MOVABLE"
        },
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KMEMCG": {"value": "___GFP_KMEMCG"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_KMEMCG": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }
    """
    Definition of GFP flags

    The decimal value of a flag will be calculated by evaluating the entries from left to right. Grouping by
    parentheses is not supported.

    Source: include/linux/gpf.h

    @note : This list os probably a mixture of different kernel versions - be carefully
    """

    gfp_reverse_lookup = []
    """
    Sorted list of flags used to do a reverse lookup.

    This list doesn't contain all flags. It contains the "useful flags" (GFP_*) as
    well as "modifier flags" (__GFP_*). "Plain flags" (___GFP_*) are not part of
    this list.

    @type: List(str)
    @see: _gfp_create_reverse_lookup()
    """

    MAX_ORDER = -1
    """
    The kernel memory allocator divides physically contiguous memory
    blocks into "zones", where each zone is a power of two number of
    pages.  This option selects the largest power of two that the kernel
    keeps in the memory allocator.

    This config option is actually maximum order plus one. For example,
    a value of 11 means that the largest free memory block is 2^10 pages.

    The value will be calculated dynamically based on the numbers of
    orders in OOMAnalyser._extract_buddyinfo().

    @see: OOMAnalyser._extract_buddyinfo().
    """

    pstable_items = [
        "pid",
        "uid",
        "tgid",
        "total_vm_pages",
        "rss_pages",
        "nr_ptes_pages",
        "swapents_pages",
        "oom_score_adj",
        "name",
        "notes",
    ]
    """Elements of the process table"""

    PAGE_ALLOC_COSTLY_ORDER = 3
    """
    Requests with order > PAGE_ALLOC_COSTLY_ORDER will never trigger the OOM-killer to satisfy the request.
    """

    pstable_html = [
        "PID",
        "UID",
        "TGID",
        "Total VM",
        "RSS",
        "Page Table Entries",
        "Swap Entries",
        "OOM Adjustment",
        "Name",
        "Notes",
    ]
    """
    Headings of the process table columns
    """

    pstable_non_ints = ["pid", "name", "notes"]
    """Columns that are not converted to an integer"""

    pstable_start = "[ pid ]"
    """
    Pattern to find the start of the process table

    :type: str
    """

    release = (3, 10, "")
    """
    Kernel release with this configuration

    The tuple contains major and minor version as well as a suffix like "-aws" or ".el7."

    The patch level isn't part of this version tuple, because I don't assume any changes in GFP flags within a patch
    release.

    @see: OOMAnalyser._choose_kernel_config()
    @type: (int, int, str)
    """

    REC_FREE_MEMORY_CHUNKS = re.compile(
        "Node (?P<node>\d+) (?P<zone>DMA|DMA32|Normal): (?P<zone_usage>.*) = (?P<total_free_kb_per_node>\d+)kB"
    )
    """RE to extract free memory chunks of a memory zone"""

    REC_OOM_BEGIN = re.compile(r"invoked oom-killer:", re.MULTILINE)
    """RE to match the first line of an OOM block"""

    REC_OOM_END = re.compile(r"^Killed process \d+", re.MULTILINE)
    """RE to match the last line of an OOM block"""

    REC_PAGE_SIZE = re.compile("Node 0 DMA: \d+\*(?P<page_size>\d+)kB")
    """RE to extract the page size from buddyinfo DMA zone"""

    REC_PROCESS_LINE = re.compile(
        r"^\[(?P<pid>[ \d]+)\]\s+(?P<uid>\d+)\s+(?P<tgid>\d+)\s+(?P<total_vm_pages>\d+)\s+(?P<rss_pages>\d+)\s+"
        r"(?P<nr_ptes_pages>\d+)\s+(?P<swapents_pages>\d+)\s+(?P<oom_score_adj>-?\d+)\s+(?P<name>.+)\s*"
    )
    """Match content of process table"""

    REC_WATERMARK = re.compile(
        "Node (?P<node>\d+) (?P<zone>DMA|DMA32|Normal) "
        "free:(?P<free>\d+)kB "
        "min:(?P<min>\d+)kB "
        "low:(?P<low>\d+)kB "
        "high:(?P<high>\d+)kB "
        ".*"
    )
    """
    RE to extract watermark information in a memory zone

    Source: mm/page_alloc.c:__show_free_areas()
    """

    watermark_start = "Node 0 DMA free:"
    """
    Pattern to find the start of the memory watermark information

    :type: str
     """

    zoneinfo_start = "Node 0 DMA: "
    """
    Pattern to find the start of the memory chunk information (buddyinfo)

    :type: str
    """

    ZONE_TYPES = ["DMA", "DMA32", "Normal", "HighMem", "Movable"]
    """
    List of memory zones

    @type: List(str)
    """

    def __init__(self):
        super().__init__()

        if self.EXTRACT_PATTERN is None:
            # Create a copy to prevent modifications on the class dictionary
            # TODO replace with self.EXTRACT_PATTERN = self.EXTRACT_PATTERN.copy() after
            #      https://github.com/QQuick/Transcrypt/issues/716 "dict does not have a copy method" is fixed
            self.EXTRACT_PATTERN = {}
            self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_BASE)

        if self.EXTRACT_PATTERN_OVERLAY:
            self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY)

        self._gfp_calc_all_values()
        self.gfp_reverse_lookup = self._gfp_create_reverse_lookup()

        self._check_mandatory_gfp_flags()

    def _gfp_calc_all_values(self):
        """
        Calculate decimal values for all GFP flags and store in in GFP_FLAGS[<flag>]["_value"]
        """
        # __pragma__ ('jsiter')
        for flag in self.GFP_FLAGS:
            value = self._gfp_flag2decimal(flag)
            self.GFP_FLAGS[flag]["_value"] = value
        # __pragma__ ('nojsiter')

    def _gfp_flag2decimal(self, flag):
        """\
        Convert a single flag into a decimal value.

        The flags can be concatenated with "|" or "~" and negated with "~". The
        flags will be processed from left to right. Parentheses are not supported.
        """
        if flag not in self.GFP_FLAGS:
            error("No definition for flag {} found".format(flag))
            return 0

        value = self.GFP_FLAGS[flag]["value"]
        if isinstance(value, int):
            return value

        tokenlist = iter(re.split("([|&])", value))
        operator = "|"  # set to process first flag
        negate_rvalue = False
        lvalue = 0
        while True:
            try:
                token = next(tokenlist)
            except StopIteration:
                break
            token = token.strip()
            if token in ["|", "&"]:
                operator = token
                continue

            if token.startswith("~"):
                token = token[1:]
                negate_rvalue = True

            if token.isdigit():
                rvalue = int(token)
            elif token.startswith("0x") and token[2:].isdigit():
                rvalue = int(token, 16)
            else:
                # it's not a decimal nor a hexadecimal value - reiterate assuming it's a flag string
                rvalue = self._gfp_flag2decimal(token)

            if negate_rvalue:
                rvalue = ~rvalue

            if operator == "|":
                lvalue |= rvalue
            elif operator == "&":
                lvalue &= rvalue

            operator = None
            negate_rvalue = False

        return lvalue

    def _gfp_create_reverse_lookup(self):
        """
        Create a sorted list of flags used to do a reverse lookup from value to the flag.

        @rtype: List(str)
        """
        # __pragma__ ('jsiter')
        useful = [
            key
            for key in self.GFP_FLAGS
            if key.startswith("GFP") and self.GFP_FLAGS[key]["_value"] != 0
        ]
        useful = sorted(
            useful, key=lambda key: self.GFP_FLAGS[key]["_value"], reverse=True
        )
        modifier = [
            key
            for key in self.GFP_FLAGS
            if key.startswith("__GFP") and self.GFP_FLAGS[key]["_value"] != 0
        ]
        modifier = sorted(
            modifier, key=lambda key: self.GFP_FLAGS[key]["_value"], reverse=True
        )
        # __pragma__ ('nojsiter')

        # useful + modifier produces a string with all values concatenated
        res = useful
        res.extend(modifier)
        return res

    def _check_mandatory_gfp_flags(self):
        """
        Check existance of mandatory flags used in
        OOMAnalyser._calc_trigger_process_values() to calculate the memory zone
        """
        if "__GFP_DMA" not in self.GFP_FLAGS:
            error(
                "Missing definition of GFP flag __GFP_DMA for kernel {}.{}.{}".format(
                    *self.release
                )
            )
        if "__GFP_DMA32" not in self.GFP_FLAGS:
            error(
                "Missing definition of GFP flag __GFP_DMA for kernel {}.{}.{}".format(
                    *self.release
                )
            )
        return


class KernelConfig_3_10(BaseKernelConfig):
    name = "Configuration for Linux kernel 3.10 or later"
    release = (3, 10, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM"
        },
        "GFP_HIGHUSER_MOVABLE": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM | __GFP_MOVABLE"
        },
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KMEMCG": {"value": "___GFP_KMEMCG"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_KMEMCG": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }


class KernelConfig_3_10_EL7(KernelConfig_3_10):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for RHEL 7 / CentOS 7 specific Linux kernel (3.10)"
    release = (3, 10, ".el7.")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM"
        },
        "GFP_HIGHUSER_MOVABLE": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM | __GFP_MOVABLE"
        },
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }

    def __init__(self):
        super().__init__()


class KernelConfig_3_16(KernelConfig_3_10):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 3.16 or later"
    release = (3, 16, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM"
        },
        "GFP_HIGHUSER_MOVABLE": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL | __GFP_HIGHMEM | __GFP_MOVABLE"
        },
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }


class KernelConfig_3_19(KernelConfig_3_16):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 3.19 or later"
    release = (3, 19, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }


class KernelConfig_4_1(KernelConfig_3_19):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.1 or later"
    release = (4, 1, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_IOFS": {"value": "__GFP_IO | __GFP_FS"},
        "GFP_KERNEL": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_WAIT | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_WAIT"},
        "GFP_NOWAIT": {"value": "GFP_ATOMIC & ~__GFP_HIGH"},
        "GFP_TEMPORARY": {
            "value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN | __GFP_NO_KSWAPD"
        },
        "GFP_USER": {"value": "__GFP_WAIT | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOACCOUNT": {"value": "___GFP_NOACCOUNT"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_NO_KSWAPD": {"value": "___GFP_NO_KSWAPD"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WAIT": {"value": "___GFP_WAIT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_WAIT": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_RECLAIMABLE": {"value": 0x80000},
        "___GFP_NOACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_NO_KSWAPD": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
    }


class KernelConfig_4_4(KernelConfig_4_1):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.4 or later"
    release = (4, 4, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN & ~__GFP_KSWAPD_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOACCOUNT": {"value": "___GFP_NOACCOUNT"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_NOACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x2000000},
    }


class KernelConfig_4_5(KernelConfig_4_4):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.5 or later"
    release = (4, 5, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN & ~__GFP_KSWAPD_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x2000000},
    }


class KernelConfig_4_6(KernelConfig_4_5):
    # Supported changes:
    #  * "mm, oom_reaper: report success/failure" (bc448e897b6d24aae32701763b8a1fe15d29fa26)
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.6 or later"
    release = (4, 6, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NORETRY | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x2000000},
    }

    # The "oom_reaper" line is optionally
    REC_OOM_END = re.compile(
        r"^((Out of memory.*|Memory cgroup out of memory): Killed process \d+|oom_reaper:)",
        re.MULTILINE,
    )

    def __init__(self):
        super().__init__()


class KernelConfig_4_8(KernelConfig_4_6):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.8 or later"
    release = (4, 8, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_OTHER_NODE": {"value": "___GFP_OTHER_NODE"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_OTHER_NODE": {"value": 0x800000},
        "___GFP_WRITE": {"value": 0x1000000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x2000000},
    }


class KernelConfig_4_9(KernelConfig_4_8):
    # Supported changes:
    #  * "mm: oom: deduplicate victim selection code for memcg and global oom" (7c5f64f84483bd13886348edda8b3e7b799a7fdb)

    name = "Configuration for Linux kernel 4.9 or later"
    release = (4, 9, "")

    EXTRACT_PATTERN_OVERLAY_49 = {
        "Details of process killed by OOM": (
            r"^(Out of memory.*|Memory cgroup out of memory): Killed process \d+ \(.*\)"
            r"(, UID \d+,)?"
            r" total-vm:(?P<killed_proc_total_vm_kb>\d+)kB, anon-rss:(?P<killed_proc_anon_rss_kb>\d+)kB, "
            r"file-rss:(?P<killed_proc_file_rss_kb>\d+)kB, shmem-rss:(?P<killed_proc_shmem_rss_kb>\d+)kB.*",
            True,
        ),
    }

    def __init__(self):
        super().__init__()
        self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY_49)


class KernelConfig_4_10(KernelConfig_4_9):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.10 or later"
    release = (4, 10, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_WRITE": {"value": 0x800000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x1000000},
    }


class KernelConfig_4_12(KernelConfig_4_10):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.12 or later"
    release = (4, 12, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_REPEAT": {"value": "___GFP_REPEAT"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_REPEAT": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_WRITE": {"value": 0x800000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x1000000},
        "___GFP_NOLOCKDEP": {"value": 0x2000000},
    }


class KernelConfig_4_13(KernelConfig_4_12):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.13 or later"
    release = (4, 13, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TEMPORARY": {
            "value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_RECLAIMABLE"
        },
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_RETRY_MAYFAIL": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_WRITE": {"value": 0x800000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x1000000},
        "___GFP_NOLOCKDEP": {"value": 0x2000000},
    }


class KernelConfig_4_14(KernelConfig_4_13):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.14 or later"
    release = (4, 14, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COLD": {"value": "___GFP_COLD"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOTRACK": {"value": "___GFP_NOTRACK"},
        "__GFP_NOTRACK_FALSE_POSITIVE": {"value": "__GFP_NOTRACK"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_COLD": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_RETRY_MAYFAIL": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_NOTRACK": {"value": 0x200000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_WRITE": {"value": 0x800000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x1000000},
        "___GFP_NOLOCKDEP": {"value": 0x2000000},
    }


class KernelConfig_4_15(KernelConfig_4_14):
    # Supported changes:
    #  * mm: consolidate page table accounting (af5b0f6a09e42c9f4fa87735f2a366748767b686)
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.15 or later"
    release = (4, 15, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_RETRY_MAYFAIL": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400000},
        "___GFP_WRITE": {"value": 0x800000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x1000000},
        "___GFP_NOLOCKDEP": {"value": 0x2000000},
    }

    # nr_ptes -> pgtables_bytes
    # pr_info("[ pid ]   uid  tgid total_vm      rss nr_ptes nr_pmds nr_puds swapents oom_score_adj name\n");
    # pr_info("[ pid ]   uid  tgid total_vm      rss pgtables_bytes swapents oom_score_adj name\n");
    REC_PROCESS_LINE = re.compile(
        r"^\[(?P<pid>[ \d]+)\]\s+(?P<uid>\d+)\s+(?P<tgid>\d+)\s+(?P<total_vm_pages>\d+)\s+(?P<rss_pages>\d+)\s+"
        r"(?P<pgtables_bytes>\d+)\s+(?P<swapents_pages>\d+)\s+(?P<oom_score_adj>-?\d+)\s+(?P<name>.+)\s*"
    )

    pstable_items = [
        "pid",
        "uid",
        "tgid",
        "total_vm_pages",
        "rss_pages",
        "pgtables_bytes",
        "swapents_pages",
        "oom_score_adj",
        "name",
        "notes",
    ]

    pstable_html = [
        "PID",
        "UID",
        "TGID",
        "Total VM",
        "RSS",
        "Page Table Bytes",
        "Swap Entries Pages",
        "OOM Adjustment",
        "Name",
        "Notes",
    ]


class KernelConfig_4_18(KernelConfig_4_15):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 4.18 or later"
    release = (4, 18, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_WRITE": {"value": 0x100},
        "___GFP_NOWARN": {"value": 0x200},
        "___GFP_RETRY_MAYFAIL": {"value": 0x400},
        "___GFP_NOFAIL": {"value": 0x800},
        "___GFP_NORETRY": {"value": 0x1000},
        "___GFP_MEMALLOC": {"value": 0x2000},
        "___GFP_COMP": {"value": 0x4000},
        "___GFP_ZERO": {"value": 0x8000},
        "___GFP_NOMEMALLOC": {"value": 0x10000},
        "___GFP_HARDWALL": {"value": 0x20000},
        "___GFP_ATOMIC": {"value": 0x80000},
        "___GFP_ACCOUNT": {"value": 0x100000},
        "___GFP_DIRECT_RECLAIM": {"value": 0x200000},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x400000},
        "___GFP_NOLOCKDEP": {"value": 0x800000},
    }


class KernelConfig_4_19(KernelConfig_4_18):
    # Supported changes:
    #  * mm, oom: describe task memory unit, larger PID pad (c3b78b11efbb2865433abf9d22c004ffe4a73f5c)

    name = "Configuration for Linux kernel 4.19 or later"
    release = (4, 19, "")

    pstable_start = "[  pid  ]"


class KernelConfig_5_0(KernelConfig_4_19):
    # Supported changes:
    #  * "mm, oom: reorganize the oom report in dump_header" (ef8444ea01d7442652f8e1b8a8b94278cb57eafd)

    name = "Configuration for Linux kernel 5.0 or later"
    release = (5, 0, "")

    EXTRACT_PATTERN_OVERLAY_50 = {
        # third last line - not integrated yet
        # oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,task_memcg=/,task=sed,pid=29481,uid=12345
        "Process killed by OOM": (
            r"^Out of memory: Killed process (?P<killed_proc_pid>\d+) \((?P<killed_proc_name>[\S ]+)\) "
            r"total-vm:(?P<killed_proc_total_vm_kb>\d+)kB, anon-rss:(?P<killed_proc_anon_rss_kb>\d+)kB, "
            r"file-rss:(?P<killed_proc_file_rss_kb>\d+)kB, shmem-rss:(?P<killed_proc_shmem_rss_kb>\d+)kB, "
            r"UID:\d+ pgtables:(?P<killed_proc_pgtables>\d+)kB oom_score_adj:(?P<killed_proc_oom_score_adj>\d+)",
            True,
        ),
    }

    def __init__(self):
        super().__init__()
        self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY_50)


class KernelConfig_5_1(KernelConfig_5_0):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 5.1 or later"
    release = (5, 1, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {"value": "GFP_HIGHUSER | __GFP_MOVABLE"},
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_ZERO": {"value": 0x100},
        "___GFP_ATOMIC": {"value": 0x200},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x800},
        "___GFP_WRITE": {"value": 0x1000},
        "___GFP_NOWARN": {"value": 0x2000},
        "___GFP_RETRY_MAYFAIL": {"value": 0x4000},
        "___GFP_NOFAIL": {"value": 0x8000},
        "___GFP_NORETRY": {"value": 0x10000},
        "___GFP_MEMALLOC": {"value": 0x20000},
        "___GFP_COMP": {"value": 0x40000},
        "___GFP_NOMEMALLOC": {"value": 0x80000},
        "___GFP_HARDWALL": {"value": 0x100000},
        "___GFP_ACCOUNT": {"value": 0x400000},
        "___GFP_NOLOCKDEP": {"value": 0x800000},
    }


class KernelConfig_5_8(KernelConfig_5_1):
    # Supported changes:
    #  * "mm/writeback: discard NR_UNSTABLE_NFS, use NR_WRITEBACK instead" (8d92890bd6b8502d6aee4b37430ae6444ade7a8c)

    name = "Configuration for Linux kernel 5.8 or later"
    release = (5, 8, "")

    EXTRACT_PATTERN_OVERLAY_58 = {
        "Overall Mem-Info (part 1)": (
            r"^Mem-Info:.*" r"(?:\n)"
            # first line (starting w/o a space)
            r"^active_anon:(?P<active_anon_pages>\d+) inactive_anon:(?P<inactive_anon_pages>\d+) "
            r"isolated_anon:(?P<isolated_anon_pages>\d+)"
            r"(?:\n)"
            # remaining lines (w/ leading space)
            r"^ active_file:(?P<active_file_pages>\d+) inactive_file:(?P<inactive_file_pages>\d+) "
            r"isolated_file:(?P<isolated_file_pages>\d+)"
            r"(?:\n)"
            r"^ unevictable:(?P<unevictable_pages>\d+) dirty:(?P<dirty_pages>\d+) writeback:(?P<writeback_pages>\d+)",
            True,
        ),
    }

    def __init__(self):
        super().__init__()
        self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY_58)


class KernelConfig_5_14(KernelConfig_5_8):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 5.14 or later"
    release = (5, 14, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {
            "value": "GFP_HIGHUSER | __GFP_MOVABLE | __GFP_SKIP_KASAN_POISON"
        },
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_SKIP_KASAN_POISON": {"value": "___GFP_SKIP_KASAN_POISON"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        "__GFP_ZEROTAGS": {"value": "___GFP_ZEROTAGS"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_ZERO": {"value": 0x100},
        "___GFP_ATOMIC": {"value": 0x200},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x800},
        "___GFP_WRITE": {"value": 0x1000},
        "___GFP_NOWARN": {"value": 0x2000},
        "___GFP_RETRY_MAYFAIL": {"value": 0x4000},
        "___GFP_NOFAIL": {"value": 0x8000},
        "___GFP_NORETRY": {"value": 0x10000},
        "___GFP_MEMALLOC": {"value": 0x20000},
        "___GFP_COMP": {"value": 0x40000},
        "___GFP_NOMEMALLOC": {"value": 0x80000},
        "___GFP_HARDWALL": {"value": 0x100000},
        "___GFP_ACCOUNT": {"value": 0x400000},
        "___GFP_ZEROTAGS": {"value": 0x800000},
        "___GFP_SKIP_KASAN_POISON": {"value": 0x1000000},
        "___GFP_NOLOCKDEP": {"value": 0x2000000},
    }


class KernelConfig_5_16(KernelConfig_5_14):
    # Supported changes:
    #  * mm/page_alloc.c: show watermark_boost of zone in zoneinfo (a6ea8b5b9f1c)

    name = "Configuration for Linux kernel 5.16 or later"
    release = (5, 16, "")

    REC_WATERMARK = re.compile(
        "Node (?P<node>\d+) (?P<zone>DMA|DMA32|Normal) "
        "free:(?P<free>\d+)kB "
        "boost:(?P<boost>\d+)kB "
        "min:(?P<min>\d+)kB "
        "low:(?P<low>\d+)kB "
        "high:(?P<high>\d+)kB "
        ".*"
    )


class KernelConfig_5_18(KernelConfig_5_16):
    # Supported changes:
    #  * update GFP flags

    name = "Configuration for Linux kernel 5.18 or later"
    release = (5, 18, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {
            "value": "GFP_HIGHUSER | __GFP_MOVABLE | __GFP_SKIP_KASAN_POISON"
        },
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_SKIP_KASAN_POISON": {"value": "___GFP_SKIP_KASAN_POISON"},
        "__GFP_SKIP_KASAN_UNPOISON": {"value": "___GFP_SKIP_KASAN_UNPOISON"},
        "__GFP_SKIP_ZERO": {"value": "___GFP_SKIP_ZERO"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        "__GFP_ZEROTAGS": {"value": "___GFP_ZEROTAGS"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_ZERO": {"value": 0x100},
        "___GFP_ATOMIC": {"value": 0x200},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x800},
        "___GFP_WRITE": {"value": 0x1000},
        "___GFP_NOWARN": {"value": 0x2000},
        "___GFP_RETRY_MAYFAIL": {"value": 0x4000},
        "___GFP_NOFAIL": {"value": 0x8000},
        "___GFP_NORETRY": {"value": 0x10000},
        "___GFP_MEMALLOC": {"value": 0x20000},
        "___GFP_COMP": {"value": 0x40000},
        "___GFP_NOMEMALLOC": {"value": 0x80000},
        "___GFP_HARDWALL": {"value": 0x100000},
        "___GFP_ACCOUNT": {"value": 0x400000},
        "___GFP_ZEROTAGS": {"value": 0x800000},
        "___GFP_SKIP_ZERO": {"value": 0x1000000},
        "___GFP_SKIP_KASAN_UNPOISON": {"value": 0x2000000},
        "___GFP_SKIP_KASAN_POISON": {"value": 0x4000000},
        "___GFP_NOLOCKDEP": {"value": 0x8000000},
    }


class KernelConfig_6_0(KernelConfig_5_18):
    # Supported changes:
    #  * update GFP flags
    #  * "mm/swap: remove swap_cache_info statistics" (442701e7058b)

    name = "Configuration for Linux kernel 6.0 or later"
    release = (6, 0, "")

    # NOTE: These flags are automatically extracted from a gfp.h file.
    #       Please do not change them manually!
    GFP_FLAGS = {
        #
        #
        # Useful GFP flag combinations:
        "GFP_ATOMIC": {"value": "__GFP_HIGH | __GFP_ATOMIC | __GFP_KSWAPD_RECLAIM"},
        "GFP_HIGHUSER": {"value": "GFP_USER | __GFP_HIGHMEM"},
        "GFP_HIGHUSER_MOVABLE": {
            "value": "GFP_HIGHUSER | __GFP_MOVABLE | __GFP_SKIP_KASAN_POISON | __GFP_SKIP_KASAN_UNPOISON"
        },
        "GFP_KERNEL": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS"},
        "GFP_KERNEL_ACCOUNT": {"value": "GFP_KERNEL | __GFP_ACCOUNT"},
        "GFP_NOFS": {"value": "__GFP_RECLAIM | __GFP_IO"},
        "GFP_NOIO": {"value": "__GFP_RECLAIM"},
        "GFP_NOWAIT": {"value": "__GFP_KSWAPD_RECLAIM"},
        "GFP_TRANSHUGE": {"value": "GFP_TRANSHUGE_LIGHT | __GFP_DIRECT_RECLAIM"},
        "GFP_TRANSHUGE_LIGHT": {
            "value": "GFP_HIGHUSER_MOVABLE | __GFP_COMP | __GFP_NOMEMALLOC | __GFP_NOWARN & ~__GFP_RECLAIM"
        },
        "GFP_USER": {"value": "__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL"},
        #
        #
        # Modifier, mobility and placement hints:
        "__GFP_ACCOUNT": {"value": "___GFP_ACCOUNT"},
        "__GFP_ATOMIC": {"value": "___GFP_ATOMIC"},
        "__GFP_COMP": {"value": "___GFP_COMP"},
        "__GFP_DIRECT_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM"},
        "__GFP_DMA": {"value": "___GFP_DMA"},
        "__GFP_DMA32": {"value": "___GFP_DMA32"},
        "__GFP_FS": {"value": "___GFP_FS"},
        "__GFP_HARDWALL": {"value": "___GFP_HARDWALL"},
        "__GFP_HIGH": {"value": "___GFP_HIGH"},
        "__GFP_HIGHMEM": {"value": "___GFP_HIGHMEM"},
        "__GFP_IO": {"value": "___GFP_IO"},
        "__GFP_KSWAPD_RECLAIM": {"value": "___GFP_KSWAPD_RECLAIM"},
        "__GFP_MEMALLOC": {"value": "___GFP_MEMALLOC"},
        "__GFP_MOVABLE": {"value": "___GFP_MOVABLE"},
        "__GFP_NOFAIL": {"value": "___GFP_NOFAIL"},
        "__GFP_NOLOCKDEP": {"value": "___GFP_NOLOCKDEP"},
        "__GFP_NOMEMALLOC": {"value": "___GFP_NOMEMALLOC"},
        "__GFP_NORETRY": {"value": "___GFP_NORETRY"},
        "__GFP_NOWARN": {"value": "___GFP_NOWARN"},
        "__GFP_RECLAIM": {"value": "___GFP_DIRECT_RECLAIM | ___GFP_KSWAPD_RECLAIM"},
        "__GFP_RECLAIMABLE": {"value": "___GFP_RECLAIMABLE"},
        "__GFP_RETRY_MAYFAIL": {"value": "___GFP_RETRY_MAYFAIL"},
        "__GFP_SKIP_KASAN_POISON": {"value": "___GFP_SKIP_KASAN_POISON"},
        "__GFP_SKIP_KASAN_UNPOISON": {"value": "___GFP_SKIP_KASAN_UNPOISON"},
        "__GFP_SKIP_ZERO": {"value": "___GFP_SKIP_ZERO"},
        "__GFP_WRITE": {"value": "___GFP_WRITE"},
        "__GFP_ZERO": {"value": "___GFP_ZERO"},
        "__GFP_ZEROTAGS": {"value": "___GFP_ZEROTAGS"},
        #
        #
        # Plain integer GFP bitmasks (for internal use only):
        "___GFP_DMA": {"value": 0x01},
        "___GFP_HIGHMEM": {"value": 0x02},
        "___GFP_DMA32": {"value": 0x04},
        "___GFP_MOVABLE": {"value": 0x08},
        "___GFP_RECLAIMABLE": {"value": 0x10},
        "___GFP_HIGH": {"value": 0x20},
        "___GFP_IO": {"value": 0x40},
        "___GFP_FS": {"value": 0x80},
        "___GFP_ZERO": {"value": 0x100},
        "___GFP_ATOMIC": {"value": 0x200},
        "___GFP_DIRECT_RECLAIM": {"value": 0x400},
        "___GFP_KSWAPD_RECLAIM": {"value": 0x800},
        "___GFP_WRITE": {"value": 0x1000},
        "___GFP_NOWARN": {"value": 0x2000},
        "___GFP_RETRY_MAYFAIL": {"value": 0x4000},
        "___GFP_NOFAIL": {"value": 0x8000},
        "___GFP_NORETRY": {"value": 0x10000},
        "___GFP_MEMALLOC": {"value": 0x20000},
        "___GFP_COMP": {"value": 0x40000},
        "___GFP_NOMEMALLOC": {"value": 0x80000},
        "___GFP_HARDWALL": {"value": 0x100000},
        "___GFP_ACCOUNT": {"value": 0x400000},
        "___GFP_ZEROTAGS": {"value": 0x800000},
        "___GFP_SKIP_ZERO": {"value": 0x1000000},
        "___GFP_SKIP_KASAN_UNPOISON": {"value": 0x2000000},
        "___GFP_SKIP_KASAN_POISON": {"value": 0x4000000},
        "___GFP_NOLOCKDEP": {"value": 0x8000000},
    }

    EXTRACT_PATTERN_OVERLAY_60 = {
        "Swap usage information": (
            r"^(?P<swap_cache_pages>\d+) pages in swap cache"
            r"(?:\n)"
            r"^Free swap  = (?P<swap_free_kb>\d+)kB"
            r"(?:\n)"
            r"^Total swap = (?P<swap_total_kb>\d+)kB",
            False,
        ),
    }

    def __init__(self):
        super().__init__()
        self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY_60)


class KernelConfig_6_1(KernelConfig_6_0):
    # Supported changes:
    #  * "mm: add NR_SECONDARY_PAGETABLE to count secondary page table uses." (ebc97a52b5d6)

    name = "Configuration for Linux kernel 6.1 or later"
    release = (6, 1, "")

    EXTRACT_PATTERN_OVERLAY_61 = {
        "Overall Mem-Info (part 2)": (
            r"^ slab_reclaimable:(?P<slab_reclaimable_pages>\d+) slab_unreclaimable:(?P<slab_unreclaimable_pages>\d+)"
            r"(?:\n)"
            r"^ mapped:(?P<mapped_pages>\d+) shmem:(?P<shmem_pages>\d+) pagetables:(?P<pagetables_pages>\d+)"
            r"(?:\n)"
            r"^ sec_pagetables:(?P<sec_pagetables>\d+) bounce:(?P<bounce_pages>\d+)"
            r"(?:\n)"
            r"^ kernel_misc_reclaimable:(?P<kernel_misc_reclaimable>\d+)"
            r"(?:\n)"
            r"^ free:(?P<free_pages>\d+) free_pcp:(?P<free_pcp_pages>\d+) free_cma:(?P<free_cma_pages>\d+)",
            True,
        ),
    }

    def __init__(self):
        super().__init__()
        self.EXTRACT_PATTERN.update(self.EXTRACT_PATTERN_OVERLAY_61)


AllKernelConfigs = [
    KernelConfig_6_1(),
    KernelConfig_6_0(),
    KernelConfig_5_18(),
    KernelConfig_5_16(),
    KernelConfig_5_14(),
    KernelConfig_5_8(),
    KernelConfig_5_1(),
    KernelConfig_5_0(),
    KernelConfig_4_15(),
    KernelConfig_4_19(),
    KernelConfig_4_18(),
    KernelConfig_4_15(),
    KernelConfig_4_14(),
    KernelConfig_4_13(),
    KernelConfig_4_12(),
    KernelConfig_4_10(),
    KernelConfig_4_9(),
    KernelConfig_4_8(),
    KernelConfig_4_6(),
    KernelConfig_4_5(),
    KernelConfig_4_4(),
    KernelConfig_4_1(),
    KernelConfig_3_19(),
    KernelConfig_3_16(),
    KernelConfig_3_10_EL7(),
    KernelConfig_3_10(),
    BaseKernelConfig(),
]
"""
Instances of all available kernel configurations.

Manually sorted from newest to oldest and from specific to general.

The last entry in this list is the base configuration as a fallback.
"""


class OOMEntity:
    """Hold whole OOM message block and provide access"""

    current_line = 0
    """Zero based index of the current line in self.lines"""

    lines = []
    """OOM text as list of lines"""

    state = OOMEntityState.unknown
    """State of the OOM after initial parsing"""

    text = ""
    """OOM as text"""

    def __init__(self, text):
        # use Unix LF only
        text = text.replace("\r\n", "\n")
        text = text.strip()
        oom_lines = text.split("\n")

        self.current_line = 0
        self.lines = oom_lines
        self.text = text

        # don't do anything if the text is empty or does not contain the leading OOM message
        if not text:
            self.state = OOMEntityState.empty
            return
        elif "invoked oom-killer:" not in text:
            self.state = OOMEntityState.invalid
            return

        oom_lines = self._remove_non_oom_lines(oom_lines)
        oom_lines = self._remove_kernel_colon(oom_lines)
        cols_to_strip = self._number_of_columns_to_strip(
            oom_lines[self._get_CPU_index(oom_lines)]
        )
        oom_lines = self._journalctl_add_leading_columns_to_meminfo(
            oom_lines, cols_to_strip
        )
        oom_lines = self._strip_needless_columns(oom_lines, cols_to_strip)
        oom_lines = self._rsyslog_unescape_lf(oom_lines)

        self.lines = oom_lines
        self.text = "\n".join(oom_lines)

        if "Killed process" in text:
            self.state = OOMEntityState.complete
        else:
            self.state = OOMEntityState.started

    def _journalctl_add_leading_columns_to_meminfo(self, oom_lines, cols_to_add):
        """
        Add leading columns to handle line breaks in journalctl output correctly.

        The output of the "Mem-Info:" block contains line breaks. journalctl breaks these lines accordingly, but
        inserts at the beginning spaces instead of date and time. As a result, removing the needless columns no longer
        works correctly.

        This function adds columns back in the affected rows so that the removal works cleanly over all rows.

        @see: _rsyslog_unescape_lf()
        """
        pattern = r"^\s+ (active_file|unevictable|slab_reclaimable|mapped|sec_pagetables|kernel_misc_reclaimable|free):.+$"
        rec = re.compile(pattern)

        add_cols = ""
        for i in range(cols_to_add):
            add_cols += "Col{} ".format(i)

        expanded_lines = []
        for line in oom_lines:
            match = rec.search(line)
            if match:
                line = "{} {}".format(add_cols, line.strip())
            expanded_lines.append(line)

        return expanded_lines

    def _get_CPU_index(self, lines):
        """
        Return the index of the first line with "CPU: "

        Depending on the OOM version the "CPU: " pattern is in second or third oom line.
        """
        for i in range(len(lines)):
            if "CPU: " in lines[i]:
                return i

        return 0

    def _number_of_columns_to_strip(self, line):
        """
        Determinate number of columns left to the OOM message to strip.

        Sometime timestamps, hostnames and or syslog tags are left to the OOM message. This columns will be count to
        strip later.
        """
        to_strip = 0
        columns = line.split(" ")

        # Examples:
        # [11686.888109] CPU: 4 PID: 29481 Comm: sed Not tainted 3.10.0-514.6.1.el7.x86_64 #1
        # Apr 01 14:13:32 mysrv kernel: CPU: 4 PID: 29481 Comm: sed Not tainted 3.10.0-514.6.1.el7.x86_64 #1
        # Apr 01 14:13:32 mysrv kernel: [11686.888109] CPU: 4 PID: 29481 Comm: sed Not tainted 3.10.0-514.6.1.el7.x86_64 #1
        try:
            # strip all excl. "CPU:"
            if "CPU:" in line:
                to_strip = columns.index("CPU:")
        except ValueError:
            pass

        return to_strip

    def _remove_non_oom_lines(self, oom_lines):
        """Remove all lines before and after OOM message block"""
        cleaned_lines = []
        in_oom_lines = False
        killed_process = False

        for line in oom_lines:
            # first line of the oom message block
            if "invoked oom-killer:" in line:
                in_oom_lines = True

            if in_oom_lines:
                cleaned_lines.append(line)

            # OOM blocks ends with the second last only or both lines
            #   Out of memory: Killed process ...
            #   oom_reaper: reaped process ...
            if "Killed process" in line:
                killed_process = True
                continue

            # next line after "Killed process \d+ ..."
            if killed_process:
                if "oom_reaper" in line:
                    break
                else:
                    # remove this line
                    del cleaned_lines[-1]
                    break

        return cleaned_lines

    def _rsyslog_unescape_lf(self, oom_lines):
        """
        Split lines at '#012' (octal representation of LF).

        The output of the "Mem-Info:" block contains line breaks. Rsyslog replaces these line breaks with their octal
        representation #012. This breaks the removal of needless columns as well as the detection of the OOM values.

        Splitting the lines (again) solves this issue.

        This feature can be controlled inside the rsyslog configuration with the directives
        $EscapeControlCharactersOnReceive, $Escape8BitCharactersOnReceive and $ControlCharactersEscapePrefix.

        @see: _journalctl_add_leading_columns_to_meminfo()
        """
        lines = []

        for line in oom_lines:
            if "#012" in line:
                lines.extend(line.split("#012"))
            else:
                lines.append(line)

        return lines

    def _remove_kernel_colon(self, oom_lines):
        """
        Remove the "kernel:" pattern w/o leading and tailing spaces.

        Some OOM messages don't have a space between "kernel:" and the process name. _strip_needless_columns() will
        fail in such cases. Therefore the pattern is removed.
        """
        oom_lines = [i.replace("kernel:", "") for i in oom_lines]
        return oom_lines

    def _strip_needless_columns(self, oom_lines, cols_to_strip=0):
        """
        Remove needless columns at the start of every line.

        This function removes all leading items w/o any relation to the OOM message like, date and time, hostname,
        syslog priority/facility.
        """
        stripped_lines = []
        for line in oom_lines:
            # remove empty lines
            if not line.strip():
                continue

            if cols_to_strip:
                # [-1] slicing needs Transcrypt operator overloading
                line = line.split(" ", cols_to_strip)[-1]  # __:opov
            stripped_lines.append(line)

        return stripped_lines

    def goto_previous_line(self):
        """Set line pointer to previous line

        If using in front of an iterator:
        The line pointer in self.current_line points to the first line of a block.
        An iterator based loop starts with a next() call (as defined by the iterator
        protocol). This causes the current line to be skipped. Therefore, the line
        pointer is set to the previous line.
        """
        if self.current_line > 0:
            self.current_line -= 1
        return

    def current(self):
        """Return the current line"""
        return self.lines[self.current_line]

    def next(self):
        """Return the next line"""
        if self.current_line + 1 < len(self.lines):
            self.current_line += 1
            return self.lines[self.current_line]
        raise StopIteration()

    def find_text(self, pattern):
        """
        Search the pattern and set the position to the first found line.
        Otherwise the position pointer won't be changed.

        :param pattern: Text to find
        :type pattern: str

        :return: True if the marker has found.
        """
        for line in self.lines:
            if pattern in line:
                self.current_line = self.lines.index(line)
                return True
        return False

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()


class OOMResult:
    """Results of an OOM analysis"""

    buddyinfo = {}
    """Information about free areas in all zones"""

    details = {}
    """Extracted result"""

    error_msg = ""
    """
    Error message

    @type: str
    """

    kconfig = BaseKernelConfig()
    """Kernel configuration"""

    kversion = None
    """
    Kernel version

    @type: str
    """

    mem_alloc_failure = OOMMemoryAllocFailureType.not_started
    """State/result of the memory allocation failure analysis

    @see: OOMAnalyser._analyse_alloc_failure()
    """

    mem_fragmented = None
    """True if the memory is heavily fragmented. This means that the higher order has no free chunks.

    @see: BaseKernelConfig.PAGE_ALLOC_COSTLY_ORDER, OOMAnalyser._check_for_memory_fragmentation()
    @type: None | bool
    """

    oom_entity = None
    """
    State of this OOM (unknown, incomplete, ...)

    :type: OOMEntityState
    """

    oom_text = None
    """
    OOM text

    @type: str
    """

    oom_type = OOMEntityType.unknown
    """
    Type of this OOM (manually or automatically triggered)

    :type: OOMEntityType
    """

    swap_active = False
    """
    Swap space active or inactive

    @type: bool
    """

    watermarks = {}
    """Memory watermark information"""


class OOMAnalyser:
    """Analyse an OOM object and calculate additional values"""

    oom_entity = None
    """
    State of this OOM (unknown, incomplete, ...)

    :type: OOMEntityState
    """

    oom_result = OOMResult()
    """
    Store details of OOM analysis

    :type: OOMResult
    """

    REC_KERNEL_VERSION = re.compile(
        r"CPU: \d+ PID: \d+ Comm: .* (Not tainted|Tainted: [A-Z ]+) (?P<kernel_version>\d[\w.-]+) #.+"
    )
    """RE to match the OOM line with kernel version"""

    REC_SPLIT_KVERSION = re.compile(
        r"(?P<kernel_version>"
        r"(?P<major>\d+)\.(?P<minor>\d+)"  # major . minor
        r"(\.\d+)?"  # optional: patch level
        r"(-[\w.-]+)?"  # optional: -rc6, -arch-1, -19-generic
        r")"
    )
    """
    RE for splitting the kernel version into parts

    Examples:
     - 5.19-rc6
     - 4.14.288
     - 5.18.6-arch1-1
     - 5.13.0-19-generic #19-Ubuntu
     - 5.13.0-1028-aws #31~20.04.1-Ubuntu
     - 3.10.0-514.6.1.el7.x86_64 #1
    """

    def __init__(self, oom):
        self.oom_entity = oom
        self.oom_result = OOMResult()

    def _identify_kernel_version(self):
        """
        Identify the used kernel version and

        @rtype: bool
        """
        match = self.REC_KERNEL_VERSION.search(self.oom_entity.text)
        if not match:
            self.oom_result.error_msg = "Failed to extract kernel version from OOM text"
            return False
        self.oom_result.kversion = match.group("kernel_version")
        return True

    def _check_kversion_greater_equal(self, kversion, min_version):
        """
        Returns True if the kernel version is greater or equal to the minimum version

        @param str kversion: Kernel version
        @param (int, int, str) min_version: Minimum version
        @rtype: bool
        """
        match = self.REC_SPLIT_KVERSION.match(kversion)

        if not match:
            self.oom_result.error_msg = (
                'Failed to extract version details from version string "%s"' % kversion
            )
            return False

        required_major = min_version[0]
        required_minor = min_version[1]
        suffix = min_version[2]
        current_major = int(match.group("major"))
        current_minor = int(match.group("minor"))

        if (required_major > current_major) or (
            required_major == current_major and required_minor > current_minor
        ):
            return False

        if bool(suffix) and (suffix not in kversion):
            return False

        return True

    def _choose_kernel_config(self):
        """
        Choose the first matching kernel configuration from AllKernelConfigs

        @see: _check_kversion_greater_equal(), AllKernelConfigs
        """
        for kcfg in AllKernelConfigs:
            if self._check_kversion_greater_equal(
                self.oom_result.kversion, kcfg.release
            ):
                self.oom_result.kconfig = kcfg
                break

        if not self.oom_result.kconfig:
            warning(
                'Failed to find a proper configuration for kernel "{}"'.format(
                    self.oom_result.kversion
                )
            )
            self.oom_result.kconfig = BaseKernelConfig()
        return

    def _check_for_empty_oom(self):
        """
        Check for an empty OOM text

        @rtype: bool
        """
        if not self.oom_entity.text:
            self.state = OOMEntityState.empty
            self.oom_result.error_msg = (
                "Empty OOM text. Please insert an OOM message block."
            )
            return False
        return True

    def _check_for_complete_oom(self):
        """
        Check if the OOM in self.oom_entity is complete and update self.oom_state accordingly

        @rtype: bool
        """
        self.oom_state = OOMEntityState.unknown
        self.oom_result.error_msg = "Unknown OOM format"

        if not self.oom_result.kconfig.REC_OOM_BEGIN.search(self.oom_entity.text):
            self.state = OOMEntityState.invalid
            self.oom_result.error_msg = "The inserted text is not a valid OOM block! The initial pattern was not found!"
            return False

        if not self.oom_result.kconfig.REC_OOM_END.search(self.oom_entity.text):
            self.state = OOMEntityState.started
            self.oom_result.error_msg = (
                "The inserted OOM is incomplete! The initial pattern was found but not the "
                "final."
            )
            return False

        self.state = OOMEntityState.complete
        self.oom_result.error_msg = None
        return True

    def _extract_block_from_next_pos(self, marker):
        """
        Extract a block that starts with the marker and contains all lines up to the next line with ":".
        :rtype: str
        """
        block = ""
        if not self.oom_entity.find_text(marker):
            return block

        line = self.oom_entity.current()
        block += "{}\n".format(line)
        for line in self.oom_entity:
            if ":" in line:
                self.oom_entity.goto_previous_line()
                break
            block += "{}\n".format(line)
        return block

    def _extract_gpf_mask(self):
        """Extract the GFP (Get Free Pages) mask"""
        if self.oom_result.details["trigger_proc_gfp_flags"] is not None:
            flags = self.oom_result.details["trigger_proc_gfp_flags"]
        else:
            flags, unknown = self._gfp_hex2flags(
                self.oom_result.details["trigger_proc_gfp_mask"],
            )
            if unknown:
                flags.append("0x{0:x}".format(unknown))
            flags = " | ".join(flags)

        self.oom_result.details["_trigger_proc_gfp_mask_decimal"] = int(
            self.oom_result.details["trigger_proc_gfp_mask"], 16
        )
        self.oom_result.details["trigger_proc_gfp_mask"] = "{} ({})".format(
            self.oom_result.details["trigger_proc_gfp_mask"], flags
        )
        # already fully processed and no own element to display -> delete otherwise an error msg will be shown
        del self.oom_result.details["trigger_proc_gfp_flags"]

        # TODO: Add check if given trigger_proc_gfp_flags is equal with calculated flags

    def _extract_from_oom_text(self):
        """Extract details from OOM message text"""

        self.oom_result.details = {}
        # __pragma__ ('jsiter')
        for k in self.oom_result.kconfig.EXTRACT_PATTERN:
            pattern, is_mandatory = self.oom_result.kconfig.EXTRACT_PATTERN[k]
            rec = re.compile(pattern, re.MULTILINE)
            match = rec.search(self.oom_entity.text)
            if match:
                self.oom_result.details.update(match.groupdict())
            elif is_mandatory:
                error(
                    'Failed to extract information from OOM text. The regular expression "{}" (pattern "{}") '
                    "does not find anything. This can lead to errors later on.".format(
                        k, pattern
                    )
                )
        # __pragma__ ('nojsiter')

        if self.oom_result.details["trigger_proc_order"] == "-1":
            self.oom_result.oom_type = OOMEntityType.manual
        else:
            self.oom_result.oom_type = OOMEntityType.automatic

        self.oom_result.details["hardware_info"] = self._extract_block_from_next_pos(
            "Hardware name:"
        )

        # strip "Call Trace" line at beginning and remove leading spaces
        call_trace = ""
        block = self._extract_block_from_next_pos("Call Trace:")
        for line in block.split("\n"):
            if line.startswith("Call Trace"):
                continue
            call_trace += "{}\n".format(line.strip())
        self.oom_result.details["call_trace"] = call_trace

        self._extract_page_size()
        self._extract_pstable()
        self._extract_gpf_mask()
        self._extract_buddyinfo()
        self._extract_watermarks()

    def _extract_page_size(self):
        """Extract page size from buddyinfo DMZ zone"""
        match = self.oom_result.kconfig.REC_PAGE_SIZE.search(self.oom_entity.text)
        if match:
            self.oom_result.details["page_size_kb"] = int(match.group("page_size"))
            self.oom_result.details["_page_size_guessed"] = False
        else:
            # educated guess
            self.oom_result.details["page_size_kb"] = 4
            self.oom_result.details["_page_size_guessed"] = True

    def _extract_pstable(self):
        """Extract process table"""
        self.oom_result.details["_pstable"] = {}
        self.oom_entity.find_text(self.oom_result.kconfig.pstable_start)
        for line in self.oom_entity:
            if not line.startswith("["):
                break
            if line.startswith(self.oom_result.kconfig.pstable_start):
                continue
            match = self.oom_result.kconfig.REC_PROCESS_LINE.match(line)
            if match:
                details = match.groupdict()
                details["notes"] = ""
                pid = details.pop("pid")
                self.oom_result.details["_pstable"][pid] = {}
                self.oom_result.details["_pstable"][pid].update(details)

    def _extract_buddyinfo(self):
        """Extract information about free areas in all zones

        The migration types "(UEM)" or similar are not evaluated. They are documented in
        mm/page_alloc.c:show_migration_types().

        This function fills:
        * OOMResult.buddyinfo with [<zone>][<order>][<node>] = <number of free chunks>
        * OOMResult.buddyinfo with [zone]["total_free_kb_per_node"][node] = int(total_free_kb_per_node)
        """
        self.oom_result.buddyinfo = {}
        buddy_info = self.oom_result.buddyinfo
        self.oom_entity.find_text(self.oom_result.kconfig.zoneinfo_start)

        self.oom_entity.goto_previous_line()
        for line in self.oom_entity:
            match = self.oom_result.kconfig.REC_FREE_MEMORY_CHUNKS.match(line)
            if not match:
                continue
            node = int(match.group("node"))
            zone = match.group("zone")

            if zone not in buddy_info:
                buddy_info[zone] = {}

            if "total_free_kb_per_node" not in buddy_info[zone]:
                buddy_info[zone]["total_free_kb_per_node"] = {}
            buddy_info[zone]["total_free_kb_per_node"][node] = int(
                int(match.group("total_free_kb_per_node"))
            )

            order = -1  # to start with 0 after the first increment in for loop
            for element in match.group("zone_usage").split(" "):
                if element.startswith("("):  # skip migration types
                    continue
                order += 1
                if order not in buddy_info[zone]:
                    buddy_info[zone][order] = {}
                count = element.split("*")[0]
                count.strip()

                buddy_info[zone][order][node] = int(count)
                if "free_chunks_total" not in buddy_info[zone][order]:
                    buddy_info[zone][order]["free_chunks_total"] = 0
                buddy_info[zone][order]["free_chunks_total"] += buddy_info[zone][order][
                    node
                ]

        # MAX_ORDER is actually maximum order plus one. For example,
        # a value of 11 means that the largest free memory block is 2^10 pages.
        # __pragma__ ('jsiter')
        max_order = 0
        for o in self.oom_result.buddyinfo["DMA"]:
            # JS: integer is sometimes a string :-/
            if (isinstance(o, str) and o.isdigit()) or isinstance(o, int):
                max_order += 1
        # __pragma__ ('nojsiter')
        self.oom_result.kconfig.MAX_ORDER = max_order

    def _extract_watermarks(self):
        """
        Extract memory watermark information from all zones

        This function fills:
        * OOMResult.watermarks with [<zone>][<node>][(free|min|low|high)] = int
        * OOMResult.watermarks with [<zone>][<node>][(lowmem_reserve)] = List(int)
        """
        self.oom_result.watermarks = {}
        watermark_info = self.oom_result.watermarks
        self.oom_entity.find_text(self.oom_result.kconfig.watermark_start)

        node = None
        zone = None
        self.oom_entity.goto_previous_line()
        for line in self.oom_entity:
            match = self.oom_result.kconfig.REC_WATERMARK.match(line)
            if not match:
                if line.startswith("lowmem_reserve[]:"):
                    # zone and node are defined in the previous round
                    watermark_info[zone][node]["lowmem_reserve"] = [
                        int(v) for v in line.split()[1:]
                    ]
                continue

            node = int(match.group("node"))
            zone = match.group("zone")
            if zone not in watermark_info:
                watermark_info[zone] = {}
            if node not in watermark_info[zone]:
                watermark_info[zone][node] = {}
            for i in ["free", "min", "low", "high"]:
                watermark_info[zone][node][i] = int(match.group(i))

    def _search_node_with_memory_shortage(self):
        """
        Search NUMA node with memory shortage: watermark "free" < "min".

        This function fills:
        * OOMResult.details["trigger_proc_numa_node"] = <int(first node with memory shortage) | None>
        """
        self.oom_result.details["trigger_proc_numa_node"] = None
        zone = self.oom_result.details["trigger_proc_mem_zone"]
        watermark_info = self.oom_result.watermarks
        if zone not in watermark_info:
            debug(
                "Missing watermark info for zone {} - skip memory analysis".format(zone)
            )
            return
        # __pragma__ ('jsiter')
        for node in watermark_info[zone]:
            if watermark_info[zone][node]["free"] < watermark_info[zone][node]["min"]:
                self.oom_result.details["trigger_proc_numa_node"] = int(node)
                return
        # __pragma__ ('nojsiter')
        return

    def _gfp_hex2flags(self, hexvalue):
        """\
        Convert the hexadecimal value into flags specified by definition

        @return: Unsorted list of flags and the sum of all unknown flags as integer
        @rtype: List(str), int
        """
        remaining = int(hexvalue, 16)
        converted_flags = []

        for flag in self.oom_result.kconfig.gfp_reverse_lookup:
            value = self.oom_result.kconfig.GFP_FLAGS[flag]["_value"]
            if (remaining & value) == value:
                # delete flag by "and" with a reverted mask
                remaining &= ~value
                converted_flags.append(flag)

        converted_flags.sort()
        return converted_flags, remaining

    def _convert_numeric_results_to_integer(self):
        """Convert all *_pages and *_kb to integer"""
        # __pragma__ ('jsiter')
        for item in self.oom_result.details:
            if self.oom_result.details[item] is None:
                self.oom_result.details[item] = "<not found>"
                continue
            if (
                item.endswith("_bytes")
                or item.endswith("_kb")
                or item.endswith("_pages")
                or item.endswith("_pid")
                or item
                in ["killed_proc_score", "trigger_proc_order", "trigger_proc_oomscore"]
            ):
                try:
                    self.oom_result.details[item] = int(self.oom_result.details[item])
                except:
                    error(
                        'Converting item "{}={}" to integer failed'.format(
                            item, self.oom_result.details[item]
                        )
                    )
        # __pragma__ ('nojsiter')

    def _convert_pstable_values_to_integer(self):
        """Convert numeric values in process table to integer values"""
        ps = self.oom_result.details["_pstable"]
        ps_index = []
        # TODO Check if transcrypt issue: pragma jsiter for the whole block "for pid_str in ps: ..."
        #      sets item in "for item in ['uid',..." to 0 instead of 'uid'
        #      jsiter is necessary to iterate over ps
        for pid_str in ps.keys():
            converted = {}
            process = ps[pid_str]
            for item in self.oom_result.kconfig.pstable_items:
                if item in self.oom_result.kconfig.pstable_non_ints:
                    continue
                try:
                    converted[item] = int(process[item])
                except:
                    if item not in process:
                        pitem = "<not in process table>"
                    else:
                        pitem = process[item]
                    error(
                        'Converting process parameter "{}={}" to integer failed'.format(
                            item, pitem
                        )
                    )

            converted["name"] = process["name"]
            converted["notes"] = process["notes"]
            pid_int = int(pid_str)
            del ps[pid_str]
            ps[pid_int] = converted
            ps_index.append(pid_int)

        ps_index.sort(key=int)
        self.oom_result.details["_pstable_index"] = ps_index

    def _check_free_chunks(self, start_with_order, zone, node):
        """Check for at least one free chunk in the current or any higher order.

        Returns True, if at lease one suitable chunk is free.
        Returns None, if buddyinfo doesn't contain information for the requested node, order or zone

        @param int start_with_order: Start checking with this order
        @param str zone: Memory zone
        @param int node: Node number
        @rtype: None|bool
        """
        if not self.oom_result.buddyinfo:
            return None
        buddyinfo = self.oom_result.buddyinfo
        if zone not in buddyinfo:
            return None

        for order in range(start_with_order, self.oom_result.kconfig.MAX_ORDER):
            if order not in buddyinfo[zone]:
                break
            if node not in buddyinfo[zone][order]:
                return None
            free_chunks = buddyinfo[zone][order][node]
            if free_chunks:
                return True
        return False

    def _check_for_memory_fragmentation(self):
        """Check for heavy memory fragmentation. This means that the higher order has no free chunks.

        Returns True, all high order chunk are in use.
        Returns False, if high order chunks are available.
        Returns None, if buddyinfo doesn't contain information for the requested node, order or zone

        @see: BaseKernelConfig.PAGE_ALLOC_COSTLY_ORDER, OOMResult.mem_fragmented
        @rtype: None|bool
        """
        zone = self.oom_result.details["trigger_proc_mem_zone"]
        node = self.oom_result.details["trigger_proc_numa_node"]
        if zone not in self.oom_result.buddyinfo:
            return None
        self.oom_result.mem_fragmented = not self._check_free_chunks(
            self.oom_result.kconfig.PAGE_ALLOC_COSTLY_ORDER, zone, node
        )
        self.oom_result.details[
            "kconfig.PAGE_ALLOC_COSTLY_ORDER"
        ] = self.oom_result.kconfig.PAGE_ALLOC_COSTLY_ORDER

    def _analyse_alloc_failure(self):
        """
        Analyse why the memory allocation could be failed.

        The code in this function is inspired by mm/page_alloc.c:__zone_watermark_ok()
        """
        self.oom_result.mem_alloc_failure = OOMMemoryAllocFailureType.not_started

        if self.oom_result.oom_type == OOMEntityType.manual:
            debug("OOM triggered manually - skip memory analysis")
            return
        if not self.oom_result.buddyinfo:
            debug("Missing buddyinfo - skip memory analysis")
            return
        if ("trigger_proc_order" not in self.oom_result.details) or (
            "trigger_proc_mem_zone" not in self.oom_result.details
        ):
            debug(
                "Missing trigger_proc_order and/or trigger_proc_mem_zone - skip memory analysis"
            )
            return
        if not self.oom_result.watermarks:
            debug("Missing watermark information - skip memory analysis")
            return

        order = self.oom_result.details["trigger_proc_order"]
        zone = self.oom_result.details["trigger_proc_mem_zone"]
        watermark_info = self.oom_result.watermarks

        # "high order" requests don't trigger OOM
        if int(order) > self.oom_result.kconfig.PAGE_ALLOC_COSTLY_ORDER:
            debug("high order requests should not trigger OOM - skip memory analysis")
            self.oom_result.mem_alloc_failure = (
                OOMMemoryAllocFailureType.skipped_high_order_dont_trigger_oom
            )
            return

        # Node with memory shortage: watermark "free" < "min"
        node = self.oom_result.details["trigger_proc_numa_node"]
        if node is None:
            return

        # the remaining code is similar to mm/page_alloc.c:__zone_watermark_ok()
        # =======================================================================

        # calculation in kB and not in pages
        free_kb = watermark_info[zone][node]["free"]
        highest_zoneidx = self.oom_result.kconfig.ZONE_TYPES.index(zone)
        lowmem_reserve = watermark_info[zone][node]["lowmem_reserve"]
        min_kb = watermark_info[zone][node]["low"]

        # reduce minimum watermark for high priority calls
        # ALLOC_HIGH == __GFP_HIGH
        gfp_mask_decimal = self.oom_result.details["_trigger_proc_gfp_mask_decimal"]
        gfp_flag_high = self.oom_result.kconfig.GFP_FLAGS["__GFP_DMA"]["_value"]
        if (gfp_mask_decimal & gfp_flag_high) == gfp_flag_high:
            min_kb -= int(min_kb / 2)

        # check watermarks, if these are not met, then a high-order request also
        # cannot go ahead even if a suitable page happened to be free.
        if free_kb <= (
            min_kb
            + (
                lowmem_reserve[highest_zoneidx]
                * self.oom_result.details["page_size_kb"]
            )
        ):
            self.oom_result.mem_alloc_failure = (
                OOMMemoryAllocFailureType.failed_below_low_watermark
            )
            return

        # For a high-order request, check at least one suitable page is free
        if not self._check_free_chunks(order, zone, node):
            self.oom_result.mem_alloc_failure = (
                OOMMemoryAllocFailureType.failed_no_free_chunks
            )
            return

        self.oom_result.mem_alloc_failure = (
            OOMMemoryAllocFailureType.failed_unknown_reason
        )

    def _calc_pstable_values(self):
        """Set additional notes to processes listed in the process table"""
        tpid = self.oom_result.details["trigger_proc_pid"]
        kpid = self.oom_result.details["killed_proc_pid"]

        # sometimes the trigger process isn't part of the process table
        if tpid in self.oom_result.details["_pstable"]:
            self.oom_result.details["_pstable"][tpid]["notes"] = "trigger process"

        # assume the killed process may also not part of the process table
        if kpid in self.oom_result.details["_pstable"]:
            self.oom_result.details["_pstable"][kpid]["notes"] = "killed process"

    def _calc_trigger_process_values(self):
        """Calculate all values related with the trigger process"""
        self.oom_result.details["trigger_proc_requested_memory_pages"] = (
            2 ** self.oom_result.details["trigger_proc_order"]
        )
        self.oom_result.details["trigger_proc_requested_memory_pages_kb"] = (
            self.oom_result.details["trigger_proc_requested_memory_pages"]
            * self.oom_result.details["page_size_kb"]
        )

        gfp_mask_decimal = self.oom_result.details["_trigger_proc_gfp_mask_decimal"]
        gfp_flag_dma = self.oom_result.kconfig.GFP_FLAGS["__GFP_DMA"]["_value"]
        gfp_flag_dma32 = self.oom_result.kconfig.GFP_FLAGS["__GFP_DMA32"]["_value"]
        if (gfp_mask_decimal & gfp_flag_dma) == gfp_flag_dma:
            zone = "DMA"
        elif (gfp_mask_decimal & gfp_flag_dma32) == gfp_flag_dma32:
            zone = "DMA32"
        else:
            zone = "Normal"
        self.oom_result.details["trigger_proc_mem_zone"] = zone

    def _calc_killed_process_values(self):
        """Calculate all values related with the killed process"""
        self.oom_result.details["killed_proc_total_rss_kb"] = (
            self.oom_result.details["killed_proc_anon_rss_kb"]
            + self.oom_result.details["killed_proc_file_rss_kb"]
            + self.oom_result.details["killed_proc_shmem_rss_kb"]
        )

        self.oom_result.details["killed_proc_rss_percent"] = int(
            100
            * self.oom_result.details["killed_proc_total_rss_kb"]
            / int(self.oom_result.details["system_total_ram_kb"])
        )

    def _calc_swap_values(self):
        """Calculate all swap related values"""
        if "swap_total_kb" in self.oom_result.details:
            self.oom_result.swap_active = self.oom_result.details["swap_total_kb"] > 0
        if not self.oom_result.swap_active:
            return

        self.oom_result.details["swap_cache_kb"] = (
            self.oom_result.details["swap_cache_pages"]
            * self.oom_result.details["page_size_kb"]
        )
        del self.oom_result.details["swap_cache_pages"]

        #  SwapUsed = SwapTotal - SwapFree - SwapCache
        self.oom_result.details["swap_used_kb"] = (
            self.oom_result.details["swap_total_kb"]
            - self.oom_result.details["swap_free_kb"]
            - self.oom_result.details["swap_cache_kb"]
        )
        self.oom_result.details["system_swap_used_percent"] = int(
            100
            * self.oom_result.details["swap_used_kb"]
            / self.oom_result.details["swap_total_kb"]
        )

    def _calc_system_values(self):
        """Calculate system memory"""

        # calculate remaining explanation values
        self.oom_result.details["system_total_ram_kb"] = (
            self.oom_result.details["ram_pages"]
            * self.oom_result.details["page_size_kb"]
        )
        if self.oom_result.swap_active:
            self.oom_result.details["system_total_ramswap_kb"] = (
                self.oom_result.details["system_total_ram_kb"]
                + self.oom_result.details["swap_total_kb"]
            )
        else:
            self.oom_result.details[
                "system_total_ramswap_kb"
            ] = self.oom_result.details["system_total_ram_kb"]

        # TODO: Current RSS calculation based on process table is probably incorrect,
        #       because it don't differentiates between processes and threads
        total_rss_pages = 0
        for pid in self.oom_result.details["_pstable"].keys():
            # convert to int to satisfy Python for unit tests
            total_rss_pages += int(
                self.oom_result.details["_pstable"][pid]["rss_pages"]
            )
        self.oom_result.details["system_total_ram_used_kb"] = (
            total_rss_pages * self.oom_result.details["page_size_kb"]
        )

        self.oom_result.details["system_total_used_percent"] = int(
            100
            * self.oom_result.details["system_total_ram_used_kb"]
            / self.oom_result.details["system_total_ram_kb"]
        )

    def _determinate_platform_and_distribution(self):
        """Determinate platform and distribution"""
        kernel_version = self.oom_result.details.get("kernel_version", "")
        if "x86_64" in kernel_version:
            self.oom_result.details["platform"] = "x86 64bit"
        else:
            self.oom_result.details["platform"] = "unknown"

        dist = "unknown"
        if ".el7uek" in kernel_version:
            dist = "Oracle Linux 7 (Unbreakable Enterprise Kernel)"
        elif ".el7" in kernel_version:
            dist = "RHEL 7/CentOS 7"
        elif ".el6" in kernel_version:
            dist = "RHEL 6/CentOS 6"
        elif ".el5" in kernel_version:
            dist = "RHEL 5/CentOS 5"
        elif "ARCH" in kernel_version:
            dist = "Arch Linux"
        elif "-generic" in kernel_version:
            dist = "Ubuntu"
        self.oom_result.details["dist"] = dist

    def _calc_from_oom_details(self):
        """
        Calculate values from already extracted details

        @see: self.details
        """
        self._convert_numeric_results_to_integer()
        self._convert_pstable_values_to_integer()
        self._calc_pstable_values()

        self._determinate_platform_and_distribution()
        self._calc_swap_values()
        self._calc_system_values()
        self._calc_trigger_process_values()
        self._calc_killed_process_values()
        self._search_node_with_memory_shortage()
        self._analyse_alloc_failure()
        self._check_for_memory_fragmentation()

    def analyse(self):
        """
        Extract and calculate values from the given OOM object

        If the return value is False, the OOM is too incomplete to perform an analysis.

        @rtype: bool
        """
        if not self._check_for_empty_oom():
            error(self.oom_result.error_msg)
            return False

        if not self._identify_kernel_version():
            error(self.oom_result.error_msg)
            return False

        self._choose_kernel_config()

        if not self._check_for_complete_oom():
            error(self.oom_result.error_msg)
            return False

        self._extract_from_oom_text()
        self._calc_from_oom_details()
        self.oom_result.oom_text = self.oom_entity.text

        return True


class SVGChart:
    """
    Creates a horizontal stacked bar chart with a legend underneath.

    The entries of the legend are arranged from left to right and from top to bottom.
    """

    cfg = dict(
        chart_height=150,
        chart_width=600,
        label_height=80,
        legend_entry_width=160,
        legend_margin=7,
        title_height=20,
        title_margin=10,
        css_class="js-mem-usage__svg",  # CSS class for SVG diagram
    )
    """Basic chart configuration"""

    # generated with Colorgorical http://vrl.cs.brown.edu/color
    colors = [
        "#aee39a",
        "#344b46",
        "#1ceaf9",
        "#5d99aa",
        "#32e195",
        "#b02949",
        "#deae9e",
        "#805257",
        "#add51f",
        "#544793",
        "#a794d3",
        "#e057e1",
        "#769b5a",
        "#76f014",
        "#621da6",
        "#ffce54",
        "#d64405",
        "#bb8801",
        "#096013",
        "#ff0087",
    ]
    """20 different colors for memory usage diagrams"""

    max_entries_per_row = 3
    """Maximum chart legend entries per row"""

    namespace = "http://www.w3.org/2000/svg"

    def __init__(self):
        super().__init__()
        self.cfg["bar_topleft_x"] = 0
        self.cfg["bar_topleft_y"] = self.cfg["title_height"] + self.cfg["title_margin"]
        self.cfg["bar_bottomleft_x"] = self.cfg["bar_topleft_x"]
        self.cfg["bar_bottomleft_y"] = (
            self.cfg["bar_topleft_y"] + self.cfg["chart_height"]
        )

        self.cfg["bar_bottomright_x"] = (
            self.cfg["bar_topleft_x"] + self.cfg["chart_width"]
        )
        self.cfg["bar_bottomright_y"] = (
            self.cfg["bar_topleft_y"] + self.cfg["chart_height"]
        )

        self.cfg["legend_topleft_x"] = self.cfg["bar_topleft_x"]
        self.cfg["legend_topleft_y"] = (
            self.cfg["bar_topleft_y"] + self.cfg["legend_margin"]
        )
        self.cfg["legend_width"] = (
            self.cfg["legend_entry_width"]
            + self.cfg["legend_margin"]
            + self.cfg["legend_entry_width"]
        )

        self.cfg["diagram_height"] = (
            self.cfg["chart_height"]
            + self.cfg["title_margin"]
            + self.cfg["title_height"]
        )
        self.cfg["diagram_width"] = self.cfg["chart_width"]

        self.cfg["title_bottommiddle_y"] = self.cfg["title_height"]
        self.cfg["title_bottommiddle_x"] = self.cfg["diagram_width"] // 2

    # __pragma__ ('kwargs')
    def create_element(self, tag, **kwargs):
        """
        Create an SVG element of the given tag.

        @note: Underscores in the argument names will be replaced by minus
        @param str tag: Type of element to be created
        @rtype: Node
        """
        element = document.createElementNS(self.namespace, tag)
        # __pragma__ ('jsiter')
        for k in kwargs:
            k2 = k.replace("_", "-")
            element.setAttribute(k2, kwargs[k])
        # __pragma__ ('nojsiter')
        return element

    # __pragma__ ('nokwargs')

    # __pragma__ ('kwargs')
    def create_element_text(self, text, **kwargs):
        """
        Create an SVG text element

        @note: Underscores in the argument names will be replaced by minus
        @param str text: Text
        @rtype: Node
        """
        element = self.create_element("text", **kwargs)
        element.textContent = text
        return element

    # __pragma__ ('nokwargs')

    def create_element_svg(self, height, width, css_class=None):
        """Return a SVG element"""
        svg = self.create_element(
            "svg",
            version="1.1",
            height=height,
            width=width,
            viewBox="0 0 {} {}".format(width, height),
        )
        if css_class:
            svg.setAttribute("class", css_class)
        return svg

    def create_rectangle(self, x, y, width, height, color=None, title=None):
        """
        Return a rect-element in a group container

        If a title is given, the container also contains a <title> element.
        """
        g = self.create_element("g")
        rect = self.create_element("rect", x=x, y=y, width=width, height=height)
        if color:
            rect.setAttribute("fill", color)
        if title:
            t = self.create_element("title")
            t.textContent = title
            g.appendChild(t)
        g.appendChild(rect)
        return g

    def create_legend_entry(self, color, desc, pos):
        """
        Create a legend entry for the given position. Both elements of the entry are grouped within a g-element.

        @param str color: Colour of the entry
        @param str desc: Description
        @param int pos: Continuous position
        @rtype: Node
        """
        label_group = self.create_element("g", id=desc)
        color_rect = self.create_rectangle(0, 0, 20, 20, color)
        label_group.appendChild(color_rect)

        desc_element = self.create_element_text(desc, x="30", y="18")
        desc_element.textContent = desc
        label_group.appendChild(desc_element)

        # move group to right position
        x, y = self.legend_calc_xy(pos)
        label_group.setAttribute("transform", "translate({}, {})".format(x, y))

        return label_group

    def legend_max_row(self, pos):
        """
        Returns the maximum number of rows in the legend

        @param int pos: Continuous position
        """
        max_row = math.ceil(pos / self.max_entries_per_row)
        return max_row

    def legend_max_col(self, pos):
        """
        Returns the maximum number of columns in the legend

        @param int pos: Continuous position
        @rtype: int
        """
        if pos < self.max_entries_per_row:
            return pos
        return self.max_entries_per_row

    def legend_calc_x(self, column):
        """
        Calculate the X-axis using the given column

        @type column: int
        @rtype: int
        """
        x = self.cfg["bar_bottomleft_x"] + self.cfg["legend_margin"]
        x += column * (self.cfg["legend_margin"] + self.cfg["legend_entry_width"])
        return x

    def legend_calc_y(self, row):
        """
        Calculate the Y-axis using the given row

        @type row: int
        @rtype: int
        """
        y = self.cfg["bar_bottomleft_y"] + self.cfg["legend_margin"]
        y += row * 40
        return y

    def legend_calc_xy(self, pos):
        """
        Calculate the X-axis and Y-axis

        @param int pos: Continuous position
        @rtype: int, int
        """
        if not pos:
            col = 0
            row = 0
        else:
            col = pos % self.max_entries_per_row
            row = math.floor(pos / self.max_entries_per_row)

        x = self.cfg["bar_bottomleft_x"] + self.cfg["legend_margin"]
        y = self.cfg["bar_bottomleft_y"] + self.cfg["legend_margin"]
        x += col * (self.cfg["legend_margin"] + self.cfg["legend_entry_width"])
        y += row * 40

        return x, y

    def generate_bar_area(self, elements):
        """
        Generate colord stacked bars. All entries are group within a g-element.

        @rtype: Node
        """
        bar_group = self.create_element(
            "g", id="bar_group", stroke="black", stroke_width=2
        )
        current_x = 0
        total_length = sum([length for unused, length in elements])

        for i, two in enumerate(elements):
            name, length = two
            color = self.colors[i % len(self.colors)]
            rect_len = int(length / total_length * self.cfg["chart_width"])
            if rect_len == 0:
                rect_len = 1
            rect = self.create_rectangle(
                current_x,
                self.cfg["bar_topleft_y"],
                rect_len,
                self.cfg["chart_height"],
                color,
                name,
            )
            current_x += rect_len
            bar_group.appendChild(rect)

        return bar_group

    def generate_legend(self, elements):
        """
        Generate a legend for all elements. All entries are group within a g-element.

        @rtype: Node
        """
        legend_group = self.create_element("g", id="legend_group")
        for i, two in enumerate(elements):
            element_name = two[0]
            color = self.colors[i % len(self.colors)]
            label_group = self.create_legend_entry(color, element_name, i)
            legend_group.appendChild(label_group)

        # re-calculate chart height after all legend entries added
        self.cfg["diagram_height"] = self.legend_calc_y(
            self.legend_max_row(len(elements))
        )

        return legend_group

    def generate_chart(self, title, *elements):
        """
        Return a SVG bar chart for all elements

        @param str title: Chart title
        @param elements: List of tuple with name and length of the entry (not normalized)
        @rtype: Node
        """
        filtered_elements = [(name, length) for name, length in elements if length > 0]
        bar_group = self.generate_bar_area(filtered_elements)
        legend_group = self.generate_legend(filtered_elements)
        svg = self.create_element_svg(
            self.cfg["diagram_height"], self.cfg["diagram_width"], self.cfg["css_class"]
        )
        chart_title = self.create_element_text(
            title,
            font_size=self.cfg["title_height"],
            font_weight="bold",
            stroke_width="0",
            text_anchor="middle",
            x=self.cfg["title_bottommiddle_x"],
            y=self.cfg["title_bottommiddle_y"],
        )
        svg.appendChild(chart_title)
        svg.appendChild(bar_group)
        svg.appendChild(legend_group)
        return svg


class OOMDisplay:
    """Display the OOM analysis"""

    # result ergibt an manchen stellen self.result.result :-/
    oom_result = OOMResult()
    """
    OOM analysis details

    @rtype: OOMResult
    """

    example_tumbleweed_swap = """\
[ 5907.004253] MonsterApp invoked oom-killer: gfp_mask=0x140dca(GFP_HIGHUSER_MOVABLE|__GFP_COMP|__GFP_ZERO), order=0, oom_score_adj=0
[ 5907.004262] CPU: 2 PID: 3271 Comm: MonsterApp Not tainted 6.0.3-1-default #1 openSUSE Tumbleweed 50a6ebc5cb1873d6b9c639843cdd1ed0089a1281
[ 5907.004266] Hardware name: QEMU Standard PC (Q35 + ICH9, 2009), BIOS 0.0.0 02/06/2015
[ 5907.004268] Call Trace:
[ 5907.004272]  <TASK>
[ 5907.004275]  dump_stack_lvl+0x44/0x5c
[ 5907.004282]  dump_header+0x4a/0x1ff
[ 5907.004286]  oom_kill_process.cold+0xb/0x10
[ 5907.004290]  out_of_memory+0x1fd/0x4d0
[ 5907.004295]  __alloc_pages_slowpath.constprop.0+0xcb0/0xe00
[ 5907.004303]  __alloc_pages+0x218/0x240
[ 5907.004308]  __folio_alloc+0x17/0x50
[ 5907.004311]  ? policy_node+0x51/0x70
[ 5907.004314]  vma_alloc_folio+0x88/0x300
[ 5907.004318]  __handle_mm_fault+0x946/0xfa0
[ 5907.004324]  handle_mm_fault+0xae/0x290
[ 5907.004327]  do_user_addr_fault+0x1ba/0x690
[ 5907.004332]  exc_page_fault+0x66/0x150
[ 5907.004337]  asm_exc_page_fault+0x22/0x30
[ 5907.004340] RIP: 0033:0x4011c1
[ 5907.004347] Code: Unable to access opcode bytes at RIP 0x401197.
[ 5907.004348] RSP: 002b:00007ffc77b3e4d0 EFLAGS: 00010206
[ 5907.004351] RAX: 00007f1d0508d000 RBX: 00007ffc77b3e608 RCX: 00007f2793922ca7
[ 5907.004353] RDX: 0000000115bfcff0 RSI: 0000000000000000 RDI: 0000000000000000
[ 5907.004354] RBP: 00007ffc77b3e4f0 R08: 00000000ffffffff R09: 0000000000000000
[ 5907.004356] R10: 00007ffc77b3e490 R11: 0000000000000202 R12: 0000000000000000
[ 5907.004357] R13: 00007ffc77b3e618 R14: 0000000000403de0 R15: 00007f2793a8b000
[ 5907.004362]  </TASK>
[ 5907.004363] Mem-Info:
[ 5907.004366] active_anon:65916 inactive_anon:861964 isolated_anon:0
                active_file:121 inactive_file:511 isolated_file:0
                unevictable:2024 dirty:16 writeback:34
                slab_reclaimable:6584 slab_unreclaimable:10454
                mapped:28 shmem:2167 pagetables:2902 bounce:0
                kernel_misc_reclaimable:0
                free:26340 free_pcp:0 free_cma:0
[ 5907.004371] Node 0 active_anon:263664kB inactive_anon:3447856kB active_file:484kB inactive_file:2044kB unevictable:8096kB isolated(anon):0kB isolated(file):0kB mapped:112kB dirty:64kB writeback:136kB shmem:8668kB shmem_thp: 0kB shmem_pmdmapped: 0kB anon_thp: 909312kB writeback_tmp:0kB kernel_stack:3104kB pagetables:11608kB all_unreclaimable? yes
[ 5907.004377] Node 0 DMA free:14336kB boost:0kB min:128kB low:160kB high:192kB reserved_highatomic:0KB active_anon:0kB inactive_anon:0kB active_file:0kB inactive_file:0kB unevictable:0kB writepending:0kB present:15996kB managed:15360kB mlocked:0kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 5907.004383] lowmem_reserve[]: 0 1946 7904 7904 7904
[ 5907.004387] Node 0 DMA32 free:40428kB boost:0kB min:16608kB low:20760kB high:24912kB reserved_highatomic:0KB active_anon:316kB inactive_anon:1967132kB active_file:32kB inactive_file:36kB unevictable:0kB writepending:320kB present:2077504kB managed:2011712kB mlocked:0kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 5907.004393] lowmem_reserve[]: 0 0 5957 5957 5957
[ 5907.004397] Node 0 Normal free:50596kB boost:0kB min:50844kB low:63552kB high:76260kB reserved_highatomic:0KB active_anon:263100kB inactive_anon:1480748kB active_file:304kB inactive_file:1876kB unevictable:8096kB writepending:64kB present:6291456kB managed:1914680kB mlocked:80kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 5907.004413] lowmem_reserve[]: 0 0 0 0 0
[ 5907.004420] Node 0 DMA: 0*4kB 0*8kB 0*16kB 0*32kB 0*64kB 0*128kB 0*256kB 0*512kB 0*1024kB 1*2048kB (M) 3*4096kB (M) = 14336kB
[ 5907.004433] Node 0 DMA32: 82*4kB (UME) 32*8kB (UME) 40*16kB (UME) 12*32kB (UE) 19*64kB (U) 14*128kB (UME) 8*256kB (UE) 4*512kB (UE) 31*1024kB (UME) 0*2048kB 0*4096kB = 40456kB
[ 5907.004472] Node 0 Normal: 847*4kB (UME) 652*8kB (UME) 285*16kB (UME) 66*32kB (UME) 53*64kB (UME) 23*128kB (UME) 9*256kB (UE) 5*512kB (UME) 24*1024kB (UM) 0*2048kB 0*4096kB = 51052kB
[ 5907.004490] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=1048576kB
[ 5907.004492] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=2048kB
[ 5907.004494] 293046 total pagecache pages
[ 5907.004495] 290241 pages in swap cache
[ 5907.004496] Free swap  = 0kB
[ 5907.004497] Total swap = 2098152kB
[ 5907.004498] 2096239 pages RAM
[ 5907.004499] 0 pages HighMem/MovableOnly
[ 5907.004500] 1110801 pages reserved
[ 5907.004500] 0 pages cma reserved
[ 5907.004501] 0 pages hwpoisoned
[ 5907.004502] Tasks state (memory values in pages):
[ 5907.004503] [  pid  ]   uid  tgid total_vm      rss pgtables_bytes swapents oom_score_adj name
[ 5907.004514] [    557]     0   557    14420      823   110592        7          -250 systemd-journal
[ 5907.004518] [    561]     0   561     8103      282    81920      274         -1000 systemd-udevd
[ 5907.004522] [    643]     0   643     2096      604    49152      360             0 haveged
[ 5907.004525] [    749]     0   749     2828       65    40960        3         -1000 auditd
[ 5907.004528] [    755]   483   755     2156      241    49152       16          -900 dbus-daemon
[ 5907.004531] [    757]     0   757    19909       80    53248        3             0 irqbalance
[ 5907.004533] [    777]     0   777     1542      119    53248       13             0 rngd
[ 5907.004540] [    782]   478   782   211645      561   151552       22             0 nscd
[ 5907.004543] [    810]     0   810     4331      280    73728       18             0 systemd-logind
[ 5907.004546] [    848]     0   848    60288        0    90112      704             0 pcscd
[ 5907.004549] [    849]     0   849     2384      237    61440       74             0 wickedd-auto4
[ 5907.004552] [    851]     0   851     2385      108    57344      208             0 wickedd-dhcp4
[ 5907.004554] [    854]     0   854     2422       63    53248      264             0 wickedd-dhcp6
[ 5907.004557] [    863]   477   863    58964       99   102400      412             0 polkitd
[ 5907.004559] [    864]     0   864     2414      131    53248      225             0 wickedd
[ 5907.004562] [    874]     0   874     2419       62    53248      264             0 wickedd-nanny
[ 5907.004564] [   1085]   472  1085     3699       36    69632      176             0 vncmanager
[ 5907.004567] [   1089]     0  1089      803       38    45056        3             0 agetty
[ 5907.004570] [   1107]     0  1107     3438       49    61440      209         -1000 sshd
[ 5907.004573] [   1108]   476  1108    21312      176    65536       36             0 chronyd
[ 5907.004576] [   1146]     0  1146    76363       58    90112      703             0 lightdm
[ 5907.004578] [   1155]     0  1155    59117      732    94208       22             0 accounts-daemon
[ 5907.004581] [   1165]     0  1165   204230     4060   450560     3612             0 Xorg.bin
[ 5907.004583] [   1201]     0  1201    40196      132    90112      640             0 lightdm
[ 5907.004586] [   1213]  1000  1213     4860      432    77824       71           100 systemd
[ 5907.004589] [   1214]  1000  1214    26171      715    94208      248           100 (sd-pam)
[ 5907.004591] [   1221]  1000  1221     1846        0    49152       69             0 icewm-session
[ 5907.004594] [   1237]  1000  1237     2056       86    49152       11           200 dbus-daemon
[ 5907.004597] [   1293]  1000  1293     1598      123    45056       14             0 ssh-agent
[ 5907.004603] [   1294]  1000  1294    38735      595    65536        3             0 gpg-agent
[ 5907.004606] [   1295]  1000  1295     6143      545    90112      314             0 icewm
[ 5907.004611] [   1298]  1000  1298     1817       49    45056       37             0 startup
[ 5907.004614] [   1300]  1000  1300     1192        0    45056       94             0 xscreensaver
[ 5907.004616] [   1302]  1000  1302     1874        0    57344      103             0 xscreensaver-sy
[ 5907.004619] [   1584]     0  1584     4143       34    65536      340             0 sshd
[ 5907.004622] [   1588]  1000  1588     4208       26    65536      418             0 sshd
[ 5907.004624] [   1590]  1000  1590     2463        0    57344      721             0 bash
[ 5907.004627] [   1739]     0  1739     4144      271    69632      104             0 sshd
[ 5907.004629] [   1742]  1000  1742     4209      267    69632      172             0 sshd
[ 5907.004632] [   1743]  1000  1743     2529      592    57344      190             0 bash
[ 5907.004635] [   3271]  1000  3271 12207676   624136  9175040   513536             0 MonsterApp
[ 5907.004638] oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,task_memcg=/user.slice/user-1000.slice/session-4.scope,task=MonsterApp,pid=3271,uid=1000
[ 5907.004654] Out of memory: Killed process 3271 (MonsterApp) total-vm:48830704kB, anon-rss:2496540kB, file-rss:4kB, shmem-rss:0kB, UID:1000 pgtables:8960kB oom_score_adj:0
"""

    example_tumbleweed_noswap = """\
[ 1400.080118] MonsterApp invoked oom-killer: gfp_mask=0x140dca(GFP_HIGHUSER_MOVABLE|__GFP_COMP|__GFP_ZERO), order=0, oom_score_adj=0
[ 1400.080125] CPU: 0 PID: 1978 Comm: MonsterApp Not tainted 6.0.3-1-default #1 openSUSE Tumbleweed 50a6ebc5cb1873d6b9c639843cdd1ed0089a1281
[ 1400.080128] Hardware name: QEMU Standard PC (Q35 + ICH9, 2009), BIOS 0.0.0 02/06/2015
[ 1400.080129] Call Trace:
[ 1400.080132]  <TASK>
[ 1400.080135]  dump_stack_lvl+0x44/0x5c
[ 1400.080141]  dump_header+0x4a/0x1ff
[ 1400.080152]  oom_kill_process.cold+0xb/0x10
[ 1400.080154]  out_of_memory+0x1fd/0x4d0
[ 1400.080159]  __alloc_pages_slowpath.constprop.0+0xcb0/0xe00
[ 1400.080165]  __alloc_pages+0x218/0x240
[ 1400.080168]  __folio_alloc+0x17/0x50
[ 1400.080171]  ? policy_node+0x51/0x70
[ 1400.080173]  vma_alloc_folio+0x88/0x300
[ 1400.080176]  __handle_mm_fault+0x946/0xfa0
[ 1400.080180]  handle_mm_fault+0xae/0x290
[ 1400.080183]  do_user_addr_fault+0x1ba/0x690
[ 1400.080188]  exc_page_fault+0x66/0x150
[ 1400.080191]  asm_exc_page_fault+0x22/0x30
[ 1400.080194] RIP: 0033:0x4011c1
[ 1400.080198] Code: Unable to access opcode bytes at RIP 0x401197.
[ 1400.080199] RSP: 002b:00007ffccb028980 EFLAGS: 00010206
[ 1400.080201] RAX: 00007fd7c06c9000 RBX: 00007ffccb028ab8 RCX: 00007fe28a591ca7
[ 1400.080203] RDX: 00000000da5c9ff0 RSI: 0000000000000000 RDI: 0000000000000000
[ 1400.080206] RBP: 00007ffccb0289a0 R08: 00000000ffffffff R09: 0000000000000000
[ 1400.080207] R10: 00007ffccb028940 R11: 0000000000000202 R12: 0000000000000000
[ 1400.080208] R13: 00007ffccb028ac8 R14: 0000000000403de0 R15: 00007fe28a6fa000
[ 1400.080212]  </TASK>
[ 1400.080213] Mem-Info:
[ 1400.080214] active_anon:970 inactive_anon:927725 isolated_anon:0
                active_file:50 inactive_file:0 isolated_file:0
                unevictable:2024 dirty:20 writeback:0
                slab_reclaimable:6559 slab_unreclaimable:10354
                mapped:0 shmem:2277 pagetables:2516 bounce:0
                kernel_misc_reclaimable:0
                free:26295 free_pcp:0 free_cma:0
[ 1400.080218] Node 0 active_anon:3880kB inactive_anon:3710900kB active_file:200kB inactive_file:0kB unevictable:8096kB isolated(anon):0kB isolated(file):0kB mapped:0kB dirty:80kB writeback:0kB shmem:9108kB shmem_thp: 0kB shmem_pmdmapped: 0kB anon_thp: 3178496kB writeback_tmp:0kB kernel_stack:3360kB pagetables:10064kB all_unreclaimable? yes
[ 1400.080222] Node 0 DMA free:14336kB boost:0kB min:128kB low:160kB high:192kB reserved_highatomic:0KB active_anon:0kB inactive_anon:0kB active_file:0kB inactive_file:0kB unevictable:0kB writepending:0kB present:15996kB managed:15360kB mlocked:0kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 1400.080226] lowmem_reserve[]: 0 1946 7904 7904 7904
[ 1400.080229] Node 0 DMA32 free:40272kB boost:0kB min:16608kB low:20760kB high:24912kB reserved_highatomic:0KB active_anon:140kB inactive_anon:1968716kB active_file:0kB inactive_file:0kB unevictable:0kB writepending:0kB present:2077504kB managed:2011712kB mlocked:0kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 1400.080233] lowmem_reserve[]: 0 0 5957 5957 5957
[ 1400.080236] Node 0 Normal free:50572kB boost:0kB min:50844kB low:63552kB high:76260kB reserved_highatomic:0KB active_anon:3740kB inactive_anon:1741752kB active_file:0kB inactive_file:356kB unevictable:8096kB writepending:80kB present:6291456kB managed:1914680kB mlocked:80kB bounce:0kB free_pcp:0kB local_pcp:0kB free_cma:0kB
[ 1400.080240] lowmem_reserve[]: 0 0 0 0 0
[ 1400.080243] Node 0 DMA: 0*4kB 0*8kB 0*16kB 0*32kB 0*64kB 0*128kB 0*256kB 0*512kB 0*1024kB 1*2048kB (M) 3*4096kB (M) = 14336kB
[ 1400.080259] Node 0 DMA32: 71*4kB (UME) 65*8kB (UME) 42*16kB (UE) 37*32kB (UE) 40*64kB (UME) 28*128kB (UME) 9*256kB (UME) 5*512kB (UME) 4*1024kB (UME) 1*2048kB (M) 5*4096kB (M) = 40292kB
[ 1400.080294] Node 0 Normal: 730*4kB (UME) 110*8kB (UME) 339*16kB (UE) 213*32kB (UE) 91*64kB (UME) 43*128kB (UME) 13*256kB (UME) 5*512kB (UE) 17*1024kB (UM) 0*2048kB 0*4096kB = 50664kB
[ 1400.080323] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=1048576kB
[ 1400.080324] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=2048kB
[ 1400.080340] 2378 total pagecache pages
[ 1400.080341] 0 pages in swap cache
[ 1400.080341] Free swap  = 0kB
[ 1400.080342] Total swap = 0kB
[ 1400.080343] 2096239 pages RAM
[ 1400.080343] 0 pages HighMem/MovableOnly
[ 1400.080344] 1110801 pages reserved
[ 1400.080344] 0 pages cma reserved
[ 1400.080345] 0 pages hwpoisoned
[ 1400.080346] Tasks state (memory values in pages):
[ 1400.080346] [  pid  ]   uid  tgid total_vm      rss pgtables_bytes swapents oom_score_adj name
[ 1400.080357] [    557]     0   557    14420      828   110592        0          -250 systemd-journal
[ 1400.080360] [    561]     0   561     8103      556    81920        0         -1000 systemd-udevd
[ 1400.080363] [    643]     0   643     2096      964    49152        0             0 haveged
[ 1400.080365] [    749]     0   749     2828       60    40960        0         -1000 auditd
[ 1400.080367] [    755]   483   755     2156      256    49152        1          -900 dbus-daemon
[ 1400.080369] [    757]     0   757    19909       83    53248        0             0 irqbalance
[ 1400.080371] [    776]     0   776    20107       61    49152        0             0 qemu-ga
[ 1400.080373] [    777]     0   777     1542      132    53248        0             0 rngd
[ 1400.080374] [    782]   478   782   211645      580   151552        0             0 nscd
[ 1400.080377] [    810]     0   810     4331      298    73728        0             0 systemd-logind
[ 1400.080393] [    848]     0   848    60288      688    90112        0             0 pcscd
[ 1400.080395] [    849]     0   849     2384      311    61440        0             0 wickedd-auto4
[ 1400.080397] [    851]     0   851     2385      316    57344        0             0 wickedd-dhcp4
[ 1400.080399] [    854]     0   854     2422      312    53248        0             0 wickedd-dhcp6
[ 1400.080400] [    863]   477   863    58964      509   102400        1             0 polkitd
[ 1400.080402] [    864]     0   864     2414      355    53248        0             0 wickedd
[ 1400.080404] [    874]     0   874     2419      326    53248        0             0 wickedd-nanny
[ 1400.080406] [   1080]     0  1080     7081      408    86016        0             0 cupsd
[ 1400.080407] [   1081]   458  1081   305359     7251   286720        0             0 matterbridge
[ 1400.080409] [   1082]   456  1082   179448     2603   110592        0             0 node_exporter
[ 1400.080411] [   1085]   472  1085     3699      212    69632        0             0 vncmanager
[ 1400.080413] [   1089]     0  1089      803       29    45056        0             0 agetty
[ 1400.080414] [   1107]     0  1107     3438      258    61440        0         -1000 sshd
[ 1400.080416] [   1108]   476  1108    21312      212    65536        0             0 chronyd
[ 1400.080418] [   1146]     0  1146    76363      761    90112        0             0 lightdm
[ 1400.080420] [   1155]     0  1155    59117      748    94208        1             0 accounts-daemon
[ 1400.080422] [   1165]     0  1165   204230     7672   450560        0             0 Xorg.bin
[ 1400.080424] [   1201]     0  1201    40196      772    90112        0             0 lightdm
[ 1400.080425] [   1213]  1000  1213     4860      503    77824        0           100 systemd
[ 1400.080427] [   1214]  1000  1214    26171      963    94208        0           100 (sd-pam)
[ 1400.080429] [   1221]  1000  1221     1846       64    49152        0             0 icewm-session
[ 1400.080431] [   1237]  1000  1237     2056       97    49152        0           200 dbus-daemon
[ 1400.080433] [   1293]  1000  1293     1598      137    45056        0             0 ssh-agent
[ 1400.080434] [   1294]  1000  1294    38735       92    65536        0             0 gpg-agent
[ 1400.080436] [   1295]  1000  1295     6143      859    90112        0             0 icewm
[ 1400.080438] [   1298]  1000  1298     1817       86    45056        0             0 startup
[ 1400.080439] [   1300]  1000  1300     1192       88    45056        0             0 xscreensaver
[ 1400.080441] [   1302]  1000  1302     1874      101    57344        0             0 xscreensaver-sy
[ 1400.080443] [   1584]     0  1584     4143      374    65536        0             0 sshd
[ 1400.080447] [   1588]  1000  1588     4208      444    65536        0             0 sshd
[ 1400.080448] [   1590]  1000  1590     2463      709    57344        0             0 bash
[ 1400.080450] [   1739]     0  1739     4144      375    69632        0             0 sshd
[ 1400.080452] [   1742]  1000  1742     4209      439    69632        0             0 sshd
[ 1400.080453] [   1743]  1000  1743     2463      718    53248        0             0 bash
[ 1400.080455] [   1978]  1000  1978 12207676   894428  7221248        0             0 MonsterApp
[ 1400.080457] oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,task_memcg=/user.slice/user-1000.slice/session-4.scope,task=MonsterApp,pid=1978,uid=1000
[ 1400.080469] Out of memory: Killed process 1978 (MonsterApp) total-vm:48830704kB, anon-rss:3577708kB, file-rss:4kB, shmem-rss:0kB, UID:1000 pgtables:7052kB oom_score_adj:0
"""

    sorted_column_number = None
    """
    Processes will sort by values in this column

    @type: int
    """

    sort_order = None
    """Sort order for process values"""

    svg_array_updown = """
<svg width="8" height="11">
  <use xlink:href="#svg_array_updown" />
</svg>
    """
    """SVG graphics with two black triangles UP and DOWN for sorting"""

    svg_array_up = """
<svg width="8" height="11">
    <use xlink:href="#svg_array_up" />
</svg>
    """
    """SVG graphics with one black triangle UP for sorting"""

    svg_array_down = """
<svg width="8" height="11">
    <use xlink:href="#svg_array_down" />
</svg>
    """
    """SVG graphics with one black triangle DOWN for sorting"""

    def __init__(self):
        self.oom = None
        self.set_html_defaults()
#        self.update_toc()

        element = document.getElementById("version")
        element.textContent = "v{}".format(VERSION)

    def _set_item(self, item):
        """
        Paste the content into HTML elements with the ID / Class that matches the item name.

        The content won't be formatted. Only suffixes for pages and kbytes are added in the singular or plural.
        """
        elements = document.getElementsByClassName(item)
        for element in elements:
            content = self.oom_result.details.get(item, "")
            if isinstance(content, str):
                content = content.strip()

            if content == "<not found>":
                row = element.parentNode
                row.classList.add("js-text--display-none")

            if item.endswith("_pages") and isinstance(content, int):
                if content == 1:
                    content = "{}&nbsp;page".format(content)
                else:
                    content = "{}&nbsp;pages".format(content)

            if item.endswith("_bytes") and isinstance(content, int):
                if content == 1:
                    content = "{}&nbsp;Byte".format(content)
                else:
                    content = "{}&nbsp;Bytes".format(content)

            if item.endswith("_kb") and isinstance(content, int):
                if content == 1:
                    content = "{}&nbsp;kByte".format(content)
                else:
                    content = "{}&nbsp;kBytes".format(content)

            if item.endswith("_percent") and isinstance(content, int):
                content = "{}&nbsp;%".format(content)

            element.innerHTML = content

        if DEBUG:
            show_element("notify_box")

#    def update_toc(self):
#        """
#        Update the TOC to show current headlines only
#
#        There are two conditions to show a h2 headline in TOC:
#         * the headline is visible
#         * the id attribute is set
#        """
#        new_toc = ""
#
#        toc_content = document.querySelectorAll("nav > ul")[0]
#
#        for element in document.querySelectorAll("h2"):
#            if not (is_visible(element) and element.id):
#                continue
#
#            new_toc += '<li><a href="#{}">{}</a></li>'.format(
#                element.id, element.textContent
#            )
#
#        toc_content.innerHTML = new_toc

    def _show_pstable(self):
        """
        Create and show the process table with additional information
        """
        # update table heading
        for i, element in enumerate(
            document.querySelectorAll("#pstable_header > tr > td")
        ):
            element.classList.remove(
                "pstable__row-pages--width",
                "pstable__row-numeric--width",
                "pstable__row-oom-score-adj--width",
            )

            key = self.oom_result.kconfig.pstable_items[i]
            if key in ["notes", "names"]:
                klass = "pstable__row-notes--width"
            elif key == "oom_score_adj":
                klass = "pstable__row-oom-score-adj--width"
            elif (
                key.endswith("_bytes") or key.endswith("_kb") or key.endswith("_pages")
            ):
                klass = "pstable__row-pages--width"
            else:
                klass = "pstable__row-numeric--width"
            element.firstChild.textContent = self.oom_result.kconfig.pstable_html[i]
            element.classList.add(klass)

        # create new table
        new_table = ""
        table_content = document.getElementById("pstable_content")
        for pid in self.oom_result.details["_pstable_index"]:
            if pid == self.oom_result.details["trigger_proc_pid"]:
                css_class = 'class="js-pstable__triggerproc--bgcolor"'
            elif pid == self.oom_result.details["killed_proc_pid"]:
                css_class = 'class="js-pstable__killedproc--bgcolor"'
            else:
                css_class = ""
            process = self.oom_result.details["_pstable"][pid]
            fmt_list = [
                process[i]
                for i in self.oom_result.kconfig.pstable_items
                if not i == "pid"
            ]
            fmt_list.insert(0, css_class)
            fmt_list.insert(1, pid)
            line = """
            <tr {}>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
                <td>{}</td>
            </tr>
            """.format(
                *fmt_list
            )
            new_table += line

        table_content.innerHTML = new_table

    def pstable_set_sort_triangle(self):
        """Set the sorting symbols for all columns in the process table"""
        for column_name in self.oom_result.kconfig.pstable_items:
            column_number = self.oom_result.kconfig.pstable_items.index(column_name)
            element_id = "js-pstable_sort_col{}".format(column_number)
            element = document.getElementById(element_id)
            if not element:
                internal_error('Missing id "{}" in process table.'.format(element_id))
                continue

            if column_number == self.sorted_column_number:
                if self.sort_order == "descending":
                    element.innerHTML = self.svg_array_down
                else:
                    element.innerHTML = self.svg_array_up
            else:
                element.innerHTML = self.svg_array_updown

    def set_html_defaults(self):
        """Reset the HTML document but don't clean elements"""

        # show all hidden elements in the result table
        show_elements("table .js-text--display-none")

        # hide all elements marked to be hidden by default
        hide_elements(".js-text--default-hide")

        # show all elements marked to be shown by default
        show_elements(".js-text--default-show")

        # clear notification box
        element = document.getElementById("notify_box")
        while element.firstChild:
            element.removeChild(element.firstChild)

        # remove svg charts
        for element_id in ("svg_swap", "svg_ram"):
            element = document.getElementById(element_id)
            while element.firstChild:
                element.removeChild(element.firstChild)

        self._clear_pstable()

    def _clear_pstable(self):
        """Clear process table"""
        element = document.getElementById("pstable_content")
        while element.firstChild:
            element.removeChild(element.firstChild)

        # reset sort triangles
        self.sorted_column_number = None
        self.sort_order = None
        self.pstable_set_sort_triangle()

        # reset table heading
        for i, element in enumerate(
            document.querySelectorAll("#pstable_header > tr > td")
        ):
            element.classList.remove(
                "pstable__row-pages--width",
                "pstable__row-numeric--width",
                "pstable__row-oom-score-adj--width",
            )
            element.firstChild.textContent = "col {}".format(i + 1)

    def copy_example_tumbleweed_swap_to_form(self):
        document.getElementById("textarea_oom").value = self.example_tumbleweed_swap

    def copy_example_tumbleweed_noswap_to_form(self):
        document.getElementById("textarea_oom").value = self.example_tumbleweed_noswap

    def reset_form(self):
        document.getElementById("textarea_oom").value = ""
        self.set_html_defaults()
#        self.update_toc()

    def toggle_oom(self, show=False):
        """Toggle the visibility of the full OOM message"""
        oom_element = document.getElementById("oom")
        row_with_oom = oom_element.parentNode.parentNode
        toggle_msg = document.getElementById("oom_toogle_msg")

        if show or row_with_oom.classList.contains("js-text--display-none"):
            row_with_oom.classList.remove("js-text--display-none")
            toggle_msg.text = "(click to hide)"
        else:
            row_with_oom.classList.add("js-text--display-none")
            toggle_msg.text = "(click to show)"

    def analyse_and_show(self):
        """Analyse the OOM text inserted into the form and show the results"""
        self.oom = OOMEntity(self.load_from_form())

        # set defaults and clear notifications
        self.set_html_defaults()

        analyser = OOMAnalyser(self.oom)
        success = analyser.analyse()
        if success:
            self.oom_result = analyser.oom_result
            self.show_oom_details()
#            self.update_toc()

    def load_from_form(self):
        """
        Return the OOM text from textarea element

        @rtype: str
        """
        element = document.getElementById("textarea_oom")
        oom_text = element.value
        return oom_text

    def show_oom_details(self):
        """
        Show all extracted details as well as additionally generated information
        """
        self._show_items()
        self._show_swap_usage()
        self._show_ram_usage()
        self._show_alloc_failure()
        self._show_memory_fragmentation()
        self._show_page_size()

        # generate process table
        self._show_pstable()
        self.pstable_set_sort_triangle()

        element = document.getElementById("oom")
        element.textContent = self.oom_result.oom_text
        self.toggle_oom(show=False)

    def _show_alloc_failure(self):
        """Show details why the memory allocation failed"""
        if (
            self.oom_result.mem_alloc_failure
            == OOMMemoryAllocFailureType.failed_below_low_watermark
        ):
            show_elements(".js-alloc-failure--show")
            show_elements(".js-alloc-failure-below-low-watermark--show")
        elif (
            self.oom_result.mem_alloc_failure
            == OOMMemoryAllocFailureType.failed_no_free_chunks
        ):
            show_elements(".js-alloc-failure--show")
            show_elements(".js-alloc-failure-no-free-chunks--show")
        elif (
            self.oom_result.mem_alloc_failure
            == OOMMemoryAllocFailureType.failed_unknown_reason
        ):
            show_elements(".js-alloc-failure--show")
            show_elements(".js-alloc-failure-unknown-reason-show")

    def _show_memory_fragmentation(self):
        """Show details about memory fragmentation"""
        if self.oom_result.mem_fragmented is None:
            return
        show_elements(".js-memory-fragmentation--show")
        if self.oom_result.mem_fragmented:
            show_elements(".js-memory-heavy-fragmentation--show")
        else:
            show_elements(".js-memory-no-heavy-fragmentation--show")
        if self.oom_result.details["trigger_proc_numa_node"] is None:
            hide_elements(".js-memory-shortage-node--hide")

    def _show_page_size(self):
        """Show page size"""
        if self.oom_result.details.get("_page_size_guessed", True):
            show_elements(".js-pagesize-guessed--show")
        else:
            show_elements(".js-pagesize-determined--show")

    def _show_ram_usage(self):
        """Generate RAM usage diagram"""
        ram_title_attr = (
            ("Active mem", "active_anon_pages"),
            ("Inactive mem", "inactive_anon_pages"),
            ("Isolated mem", "isolated_anon_pages"),
            ("Active PC", "active_file_pages"),
            ("Inactive PC", "inactive_file_pages"),
            ("Isolated PC", "isolated_file_pages"),
            ("Unevictable", "unevictable_pages"),
            ("Dirty", "dirty_pages"),
            ("Writeback", "writeback_pages"),
            ("Unstable", "unstable_pages"),
            ("Slab reclaimable", "slab_reclaimable_pages"),
            ("Slab unreclaimable", "slab_unreclaimable_pages"),
            ("Mapped", "mapped_pages"),
            ("Shared", "shmem_pages"),
            ("Pagetable", "pagetables_pages"),
            ("Bounce", "bounce_pages"),
            ("Free", "free_pages"),
            ("Free PCP", "free_pcp_pages"),
            ("Free CMA", "free_cma_pages"),
        )
        chart_elements = [
            (title, self.oom_result.details[value])
            for title, value in ram_title_attr
            if value in self.oom_result.details
        ]
        svg = SVGChart()
        svg_ram = svg.generate_chart("RAM Summary", *chart_elements)
        elem_svg_ram = document.getElementById("svg_ram")
        elem_svg_ram.appendChild(svg_ram)

    def _show_swap_usage(self):
        """Show/hide swap space and generate usage diagram"""
        if self.oom_result.swap_active:
            # generate swap usage diagram
            svg = SVGChart()
            svg_swap = svg.generate_chart(
                "Swap Summary",
                ("Swap Used", self.oom_result.details["swap_used_kb"]),
                ("Swap Free", self.oom_result.details["swap_free_kb"]),
                ("Swap Cached", self.oom_result.details["swap_cache_kb"]),
            )
            elem_svg_swap = document.getElementById("svg_swap")
            elem_svg_swap.appendChild(svg_swap)
            show_elements(".js-swap-active--show")
        else:
            show_elements(".js-swap-inactive--show")

    def _show_items(self):
        """Switch to output view and show most items"""
        hide_element("input")
        show_element("analysis")
        if self.oom_result.oom_type == OOMEntityType.manual:
            show_elements(".js-oom-manual--show")
        else:
            show_elements(".js-oom-automatic--show")

        for item in self.oom_result.details.keys():
            # ignore internal items
            if item.startswith("_"):
                continue
            self._set_item(item)

        # Hide "OOM Score" if not available
        # since KernelConfig_5_0.EXTRACT_PATTERN_OVERLAY_50['Process killed by OOM']
        if "killed_proc_score" in self.oom_result.details:
            show_elements(".js-killed-proc-score--show")

    def sort_pstable(self, column_number):
        """
        Sort process table by values

        :param int column_number: Number of column to sort
        """
        # TODO Check operator overloading
        #      Operator overloading (Pragma opov) does not work in this context.
        #      self.oom_result.kconfig.pstable_items + ['notes'] will compile to a string
        #      "pid,uid,tgid,total_vm_pages,rss_pages,nr_ptes_pages,swapents_pages,oom_score_adjNotes" and not to an
        #      array
        ps_table_and_notes = self.oom_result.kconfig.pstable_items[:]
        ps_table_and_notes.append("notes")
        column_name = ps_table_and_notes[column_number]
        if column_name not in ps_table_and_notes:
            internal_error(
                'Can not sort process table with an unknown column name "{}"'.format(
                    column_name
                )
            )
            return

        # reset sort order if the column has changes
        if column_number != self.sorted_column_number:
            self.sort_order = None
        self.sorted_column_number = column_number

        if not self.sort_order or self.sort_order == "descending":
            self.sort_order = "ascending"
            self.sort_psindex_by_column(column_name)
        else:
            self.sort_order = "descending"
            self.sort_psindex_by_column(column_name, True)

        self._show_pstable()
        self.pstable_set_sort_triangle()

    def sort_psindex_by_column(self, column_name, reverse=False):
        """
        Sort the pid list '_pstable_index' based on the values in the process dict '_pstable'.

        Is uses bubble sort with all disadvantages but just a few lines of code
        """
        ps = self.oom_result.details["_pstable"]
        ps_index = self.oom_result.details["_pstable_index"]

        def getvalue(column, pos):
            if column == "pid":
                value = ps_index[pos]
            else:
                value = ps[ps_index[pos]][column]
            # JS sorts alphanumeric by default, convert values explicit to integers to sort numerically
            if (
                column not in self.oom_result.kconfig.pstable_non_ints
                and value is not js_undefined
            ):
                value = int(value)
            return value

        # We set swapped to True so the loop looks runs at least once
        swapped = True
        while swapped:
            swapped = False
            for i in range(len(ps_index) - 1):
                v1 = getvalue(column_name, i)
                v2 = getvalue(column_name, i + 1)

                if (not reverse and v1 > v2) or (reverse and v1 < v2):
                    # Swap the elements
                    ps_index[i], ps_index[i + 1] = ps_index[i + 1], ps_index[i]

                    # Set the flag to True so we'll loop again
                    swapped = True


OOMDisplayInstance = OOMDisplay()
