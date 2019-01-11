# -*- coding: utf-8 -*-
"""
web2ldap plugin classes for attributes defined in SCHAC

See https://www.terena.org/activities/tf-emc2/schac.html
"""

from __future__ import absolute_import

import re
import datetime

from web2ldap.app.schema.syntaxes import \
    DateOfBirth, \
    DirectoryString, \
    IA5String, \
    NumericString, \
    CountryString, \
    DNSDomain, \
    NumstringDate, \
    syntax_registry
from web2ldap.app.plugins.msperson import Gender


syntax_registry.registerAttrType(
    CountryString.oid, [
        '1.3.6.1.4.1.25178.1.2.5',  # schacCountryOfCitizenship
        '1.3.6.1.4.1.25178.1.2.11', # schacCountryOfResidence
    ]
)

syntax_registry.registerAttrType(
    DNSDomain.oid, [
        '1.3.6.1.4.1.25178.1.2.9', # schacHomeOrganization
    ]
)

class SchacMotherTongue(IA5String):
    oid = 'SchacMotherTongue-oid'
    desc = 'Language tag of the language a person learns first (see RFC 3066).'
    reObj = re.compile('^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{2,8})*$')

syntax_registry.registerAttrType(
    SchacMotherTongue.oid, [
        '1.3.6.1.4.1.25178.1.2.1', # schacMotherTongue
    ]
)


syntax_registry.registerAttrType(
    Gender.oid, [
        '1.3.6.1.4.1.25178.1.2.2', # schacGender
    ]
)


class SchacDateOfBirth(DateOfBirth):
    oid = 'SchacDateOfBirth-oid'
    desc = 'Date of birth: syntax YYYYMMDD'
    storageFormat = '%Y%m%d'

syntax_registry.registerAttrType(
    SchacDateOfBirth.oid, [
        '1.3.6.1.4.1.25178.1.2.3', # schacDateOfBirth
    ]
)


class SchacYearOfBirth(NumericString):
    oid = 'SchacYearOfBirth-oid'
    desc = 'Year of birth: syntax YYYY'
    maxLen = 4
    reObj = re.compile('^[0-9]{4}$')

    def _validate(self, attrValue):
        try:
            birth_year = int(attrValue)
        except ValueError:
            return False
        return birth_year <= datetime.date.today().year

syntax_registry.registerAttrType(
    SchacYearOfBirth.oid, [
        '1.3.6.1.4.1.25178.1.0.2.3', # schacYearOfBirth
    ]
)


class SchacUrn(DirectoryString):
    oid = 'SchacUrn-oid'
    desc = 'Generic URN for SCHAC'
    reObj = re.compile('^urn:mace:terena.org:schac:.+$')

syntax_registry.registerAttrType(
    SchacUrn.oid, [
        '1.3.6.1.4.1.25178.1.2.10', # schacHomeOrganizationType
        '1.3.6.1.4.1.25178.1.2.13', # schacPersonalPosition
        '1.3.6.1.4.1.25178.1.2.14', # schacPersonalUniqueCode
        '1.3.6.1.4.1.25178.1.2.15', # schacPersonalUniqueID
        '1.3.6.1.4.1.25178.1.2.19', # schacUserStatus
    ]
)


# Register all syntax classes in this module
for name in dir():
    syntax_registry.registerSyntaxClass(eval(name))
