# Third Party Notices

This software includes third-party components under various licenses.

## Notice Summary

This document provides the required legal notices for third-party software included in or used by this project. The full license text for each component is provided below.

---

## Permissive Licenses

### MIT License

The following components are licensed under the MIT License:

- fastapi
- pydantic
- uvicorn
- click
- pytest
- black
- ruff
- PyYAML
- PyJWT
- faiss-cpu
- Automat
- Twisted
- constantly

```
MIT License

Copyright (c) [Year] [Copyright Holders]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### BSD 3-Clause License

The following components are licensed under the BSD 3-Clause License:

- numpy
- pandas
- scikit-learn
- Jinja2
- MarkupSafe
- Babel
- click
- python-dotenv

```
BSD 3-Clause License

Copyright (c) [Year], [Copyright Holders]
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### Apache License 2.0

The following components are licensed under the Apache License 2.0:

- streamlit
- transformers
- sentence-transformers
- requests
- cryptography (dual licensed with BSD)
- bcrypt
- distro
- cloud-init (dual licensed with GPLv3)

```
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Copyleft Licenses

### GNU Lesser General Public License (LGPL)

The following components are licensed under various versions of the LGPL:

- PyGObject (LGPL v2.1+)
- chardet (LGPL v2.1)
- systemd-python (LGPL v2+)
- launchpadlib (LGPL v3)
- lazr.restfulclient (LGPL v3)
- lazr.uri (LGPL v3)
- wadllib (LGPL v3)

```
GNU LESSER GENERAL PUBLIC LICENSE
Version 3, 29 June 2007

Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
Everyone is permitted to copy and distribute verbatim copies
of this license document, but changing it is not allowed.

This version of the GNU Lesser General Public License incorporates
the terms and conditions of version 3 of the GNU General Public
License.

[Full LGPL text available at: https://www.gnu.org/licenses/lgpl-3.0.txt]
```

**IMPORTANT**: These LGPL components are used as libraries and are dynamically linked. You have the right to:
1. Use a modified version of these libraries
2. Reverse engineer for debugging modifications
3. Receive the source code upon request

### GNU General Public License (GPL)

The following system packages are licensed under the GPL:

- python-apt (GPL v2+)
- ubuntu-pro-client (GPL v3)

**Note**: These are system utilities not distributed with the application.

---

## Other Licenses

### Mozilla Public License 2.0

- certifi

```
Mozilla Public License Version 2.0

1. Definitions
[Full MPL 2.0 text available at: https://mozilla.org/MPL/2.0/]
```

### Python Software Foundation License

- numpy (portions)
- scipy (portions)

### Historical Permission Notice and Disclaimer (HPND)

- pillow

```
Permission to use, copy, modify, and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appear in all copies and that
both that copyright notice and this permission notice appear in
supporting documentation, and that the name of the copyright holder
not be used in advertising or publicity pertaining to distribution
of the software without specific, written prior permission.
```

### Zope Public License 2.1

- zope.interface

---

## Components with Unknown or Unspecified Licenses

The following packages have unclear licensing. We are working to clarify their status:

- PyPDF2
- attrs
- blinker
- colorama
- distro-info
- filelock
- fsspec
- hf-xet
- idna
- markdown-it-py
- mdurl
- packaging
- pdfminer.six
- pdfplumber
- pyparsing
- regex
- safetensors
- service-identity
- setuptools
- tokenizers
- tqdm
- typing_extensions
- urllib3
- zipp

**Action Required**: These packages are under review for license compliance.

---

## Warranty Disclaimer

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Updates and Modifications

This notice file is maintained as part of the project's compliance process.

- Last Updated: 2025-10-29
- Generated by: scripts/scan_licenses.py
- Review Cycle: Monthly

For questions about third-party licenses, please contact the legal/compliance team.

---

*End of Third Party Notices*