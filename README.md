# openSUSE OOMAnalyser

## Introduction

This is a forked version of [Carsten Grohmann's OOMAnalyser](https://git.sr.ht/~carstengrohmann/OOMAnalyser) targeting SUSE based operating systems.

It is a small project to transform the OOM message of a Linux kernel into a more user-friendly format.

OOMAnalyser consists of a web page into whose input field the OOM message is copied. JavaScript code extracts the data
from it and displays the details. All processing takes place in the browser. No data is transferred to external servers.
This makes it possible to use a locally stored copy of the website for analysis.

This project is written in [Python](https://www.python.org) and uses [Transcrypt](https://www.transcrypt.org/)  to
translate Python code into JavaScript.

The current online version is available at [https://www.carstengrohmann.de/oom/](https://www.carstengrohmann.de/oom/) .


## Installation

Installing OOMAnalyser is quite easy since OOMAnalyser consists only of two files, an HTML file and a JavaScript file.
Both can be stored locally to use OOMAnalyser without an Internet connection.

### Installation steps

 1. Open [https://www.carstengrohmann.de/oom/](https://www.carstengrohmann.de/oom/) in a browser
 2. Browse down to the paragraph "Local Installation" at the end of the document
 3. Download the HTML file and the JavaScript file to the main directory
 4. Open the file `OOMAnalyser.html` in your favourite browser


## Building OOMAnalyser

### Requirements

 * [Python](http://www.python.org) 3.7
 * [Transcrypt](https://www.transcrypt.org/) 3.7
 * [Rollup](https://rollupjs.org/)


### Prepare the build environment

 * Clone the repository:

        # git clone https://git.sr.ht/~carstengrohmann/OOMAnalyser

 * Set up the Python virtual environment:

        # virtualenv env
        # . env/bin/activate
        # env/bin/pip install -Ur requirements.txt

        or

        # make venv

### Build OOMAnalyser

```
# . env/bin/activate
# transcrypt --build --map --nomin -e 6 OOMAnalyser.py
# rollup --config rollup.config.mjs

or

# make build
```

### Usage

 * Change into the source directory and start your own small web server.

 * Start Python built-in web server:

        # python3 -m http.server 8080 --bind 127.0.0.1

        or

        # make websrv

 * Open the URL http://localhost:8080/OOMAnalyser.html in your favorite browser.


## Publish a new release
### Naming

* `NEW_VERSION` - Version string of the new version e.g. `0.5.0`
* `NEW_GIT_VERSION` - Git version string of the new version e.g. `v0.5.0`

### Steps
 1. Commit all open changes
 2. Updating the documentation in `README.md` and `OOMAnalyser.html` and commit changes

        # git commit -m "Update documentation"

 3. Update version number in `OOMAnalyser.py` and `Makefile`

        # git commit -m "Bump version number to <NEW_VERSION>"

 4. Create a new annotated git tag with shortened changelog

        # git tag -a <NEW_GIT_VERSION>

 5. Push changes into public repositories

        # git push
        # git push origin --tags

 6. Create release packages in zip and tar.gz format

        # make release

 7. Create release on SourceHut & GitHub

 8. Start a new development cycle by setting new version numbers


## Resources

 * [Transcrypt](https://www.transcrypt.org/)
 * [Linux man pages online](https://man7.org/)
 * [Decoding the Linux kernel's page allocation failure messages](https://utcc.utoronto.ca/~cks/space/blog/linux/DecodingPageAllocFailures)
 * [Linux Kernel OOM Log Analysis](http://elearningmedium.com/linux-kernel-oom-log-analysis/)


## Known Bugs/Issues

Check the project [issue tracker](https://todo.sr.ht/~carstengrohmann/OOMAnalyser)
for current open bugs. New bugs can be reported there also.


## License

This project is licensed under the MIT license.

> Copyright (c) 2017-2023 Carsten Grohmann,  mail <add at here> carstengrohmann.de
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in
> the Software without restriction, including without limitation the rights to
> use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
> of the Software, and to permit persons to whom the Software is furnished to do
> so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Enjoy!
Carsten Grohmann
