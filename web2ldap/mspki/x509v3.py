"""
x509v3.py - basic classes for X.509v3 extensions

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2019 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import absolute_import

from web2ldap.web import escape_html
# Pisces
from web2ldap.pisces import asn1
# mspki itself
from . import x509


def htmlize(e):
    """Display certificate extension object e with HTML"""
    if hasattr(e, 'html'):
        return e.html()
    return escape_html(str(e))


class Extension(asn1.Sequence):
    """
    Extension  ::=  SEQUENCE  {
         extnID      OBJECT IDENTIFIER,
         critical    BOOLEAN DEFAULT FALSE,
         extnValue   OCTET STRING  }
    """

    def __init__(self, val):
        asn1.Sequence.__init__(self, val)
        self.extnId = self.val[0]
        if len(self.val) == 3:
            self.critical, evo = self.val[1], self.val[2]
        elif len(self.val) == 2:
            self.critical, evo = None, self.val[1]
        else:
            raise ValueError, 'X.509v3 extension field has length %d' % len(self.val)
        extnId_str = str(self.extnId)
        if oidreg.has_key(extnId_str):
            try:
                self.extnValue = oidreg[extnId_str](asn1.parse(evo.val))
            except Exception:
                # If parsing known extension fails fall-back to generic parsing
                self.extnValue = asn1.parse(evo.val)
        else:
            self.extnValue = asn1.parse(evo.val)

    def __repr__(self):
        return '<%s.%s: %s: %s%s>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.extnId,
            repr(self.extnValue),
            ' (CRITICAL)'*(self.critical == 1)
        )

    def html(self):
        if hasattr(self, 'extnValue'):
            if hasattr(self.extnValue, 'html'):
                extnValue_html = self.extnValue.html()
            else:
                extnValue_html = escape_html(str(self.extnValue))
        else:
            extnValue_html = ''
        return '<dt>%s (%s)</dt><dd>%s</dd>' % (
            self.extnValue.__class__.__name__,
            self.extnId,
            extnValue_html,
        )


class Extensions(asn1.Sequence):
    """
    Extensions  ::=  SEQUENCE SIZE (1..MAX) OF Extension
    """

    def __init__(self, val):
        for i in range(len(val)):
            val[i] = Extension(val[i])
        asn1.Sequence.__init__(self, val)

    def __str__(self):
        return ', '.join(map(str, self.val))

    def __repr__(self):
        return '{%s}' % ', '.join(map(repr, self.val))

    def html(self):
        return '<ul>\n%s\n</ul>\n' % (
            '\n'.join([
                '<li>%s</li>' % (htmlize(x))
                for x in self.val
            ])
        )


class Certificate(x509.Certificate):
    """
    Class for X.509v3 certificates with extensions

    Certificate  ::=  SEQUENCE  {
         tbsCertificate       TBSCertificate,
         signatureAlgorithm   AlgorithmIdentifier,
         signatureValue       BIT STRING  }

    TBSCertificate  ::=  SEQUENCE  {
         version         [0]  EXPLICIT Version DEFAULT v1,
         serialNumber         CertificateSerialNumber,
         signature            AlgorithmIdentifier,
         issuer               Name,
         validity             Validity,
         subject              Name,
         subjectPublicKeyInfo SubjectPublicKeyInfo,
         issuerUniqueID  [1]  IMPLICIT UniqueIdentifier OPTIONAL,
                              -- If present, version shall be v2 or v3
         subjectUniqueID [2]  IMPLICIT UniqueIdentifier OPTIONAL,
                              -- If present, version shall be v2 or v3
         extensions      [3]  EXPLICIT Extensions OPTIONAL
                              -- If present, version shall be v3
         }
    """

    def extensions(self):
        """Return extracted X.509v3 extensions"""
        if int(self.version()) < 3:
            return None
        for i in self.tbsCertificate[self._tbsoffset+6:len(self.tbsCertificate)]:
            # find first occurence of tag [3]
            if hasattr(i, 'tag') and i.tag == 3:
                return Extensions(i.val)
        return None


class CRL(x509.CRL):
    """
    Class for X.509v2 CRLs with extensions

    CertificateList  ::=  SEQUENCE  {
         tbsCertList          TBSCertList,
         signatureAlgorithm   AlgorithmIdentifier,
         signatureValue       BIT STRING  }

    TBSCertList  ::=  SEQUENCE  {
         version                 Version OPTIONAL,
                                      -- if present, shall be v2
         signature               AlgorithmIdentifier,
         issuer                  Name,
         thisUpdate              Time,
         nextUpdate              Time OPTIONAL,
         revokedCertificates     SEQUENCE OF SEQUENCE  {
              userCertificate         CertificateSerialNumber,
              revocationDate          Time,
              crlEntryExtensions      Extensions OPTIONAL
                                            -- if present, shall be v2
                                   }  OPTIONAL,
         crlExtensions           [0]  EXPLICIT Extensions OPTIONAL
                                            -- if present, shall be v2
                                   }

    """

    def crlExtensions(self):
        """Return extracted X.509v3 extensions"""
        for i in self.tbsCertList[self._tbsoffset+5:len(self.tbsCertList)]:
            # find first occurence of tag [0]
            if hasattr(i, 'tag') and i.tag == 0:
                return Extensions(i.val)
        return None


# now pull all oidreg's in other modules holding classes
# for various X.509v3 extension
from . import pkix, vendorext

oidreg = {
    # PKIX extensions
    '2.5.29.9': pkix.SubjectDirectoryAttributes,
    '2.5.29.10': pkix.BasicConstraints,
    '2.5.29.14': pkix.SubjectKeyIdentifier,
    '2.5.29.15': pkix.KeyUsage,
    '2.5.29.16': pkix.PrivateKeyUsagePeriod,
    '2.5.29.17': pkix.SubjectAltName,
    '2.5.29.18': pkix.IssuerAltName,
    '2.5.29.19': pkix.BasicConstraints,
    '2.5.29.20': pkix.CRLNumber,
    '2.5.29.28': pkix.IssuingDistributionPoint,
    '2.5.29.31': pkix.CRLDistributionPoints,
    '2.5.29.32': pkix.CertificatePolicies,
    '2.5.29.35': pkix.AuthorityKeyIdentifier,
    '2.5.29.36': pkix.PolicyConstraints,
    '2.5.29.37': pkix.ExtendedKeyUsage,
    '2.5.29.21': pkix.CRLReason,
    '2.5.29.29': pkix.CertificateIssuer,
    '1.3.6.1.5.5.7.1.1': pkix.AuthorityInfoAccessSyntax,
    # Entrust extensions
    '1.2.840.113533.7.65.0': vendorext.EntrustVersInfo,
}
