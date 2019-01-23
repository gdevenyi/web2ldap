# -*- coding: utf-8 -*-
"""
web2ldap plugin classes for dynamic entries (see RFC 2589)
"""

from __future__ import absolute_import

import time

from web2ldap.utctime import strftimeiso8601

from web2ldap.app.schema.syntaxes import Timespan, DistinguishedName, syntax_registry


class EntryTTL(Timespan):
    oid = 'EntryTTL-oid'
    desc = 'Time-to-live of dynamic entry'

    def displayValue(self, valueindex=0, commandbutton=False):
        expiration_time = time.time()+int(self._av)
        return '%s, expires %s' % (
            Timespan.displayValue(self, valueindex, commandbutton),
            strftimeiso8601(time.gmtime(expiration_time)),
        )

syntax_registry.reg_at(
    EntryTTL.oid, [
        '1.3.6.1.4.1.1466.101.119.3', # entryTTL
    ]
)


class DynamicSubtrees(DistinguishedName):
    oid = 'DynamicSubtrees-oid'
    desc = 'Subtrees with dynamic entries'

    def _additional_links(self):
        r = DistinguishedName._additional_links(self)
        r.append(
            self._app.anchor(
                'search', 'Search',
                [
                    ('dn', self.av_u),
                    ('search_root', self.av_u),
                    ('filterstr', u'(objectClass=dynamicObject)'),
                    ('searchform_mode', u'exp'),
                ],
                title=u'Search for dynamic entries',
            ),
        )
        return r

syntax_registry.reg_at(
    DynamicSubtrees.oid, [
        '1.3.6.1.4.1.1466.101.119.4', # dynamicSubtrees
    ]
)


# Register all syntax classes in this module
syntax_registry.reg_syntaxes(__name__)
