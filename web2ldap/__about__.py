# -*- coding: utf-8 -*-
"""
Meta information about web2ldap

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2019 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

import collections

VersionInfo = collections.namedtuple('version_info', ('major', 'minor', 'micro'))
__version_info__ = VersionInfo(
    major=1,
    minor=4,
    micro=19,
)
__version__ = '.'.join(str(val) for val in __version_info__)
__author__ = u'Michael Stroeder'
__mail__ = u'michael@stroeder.com'
__copyright__ = u'(C) 2017-2019 by Michael Ströder <michael@stroeder.com>'
__license__ = 'Apache-2.0'

__all__ = [
    '__version_info__',
    '__version__',
    '__author__',
    '__mail__',
    '__license__',
    '__copyright__',
]
