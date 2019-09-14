# -*- coding: utf-8 -*-
"""
web2ldap.app.form: class for web2ldap input form handling

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2019 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

import re
import http.cookies

import ldap0.ldif
import ldap0.schema
from ldap0.pw import random_string

import web2ldapcnf

from web2ldap.web import escape_html
import web2ldap.ldaputil
from web2ldap.ldaputil.oidreg import OID_REG
import web2ldap.ldapsession
import web2ldap.ldaputil.passwd
import web2ldap.app.core
import web2ldap.app.gui
import web2ldap.app.searchform
import web2ldap.app.params
import web2ldap.app.session
from web2ldap.app.session import session_store
from web2ldap.ldapsession import AVAILABLE_BOOLEAN_CONTROLS
import web2ldap.web.forms
from web2ldap.web.forms import \
    Input, \
    Field, \
    Textarea, \
    BytesInput, \
    Select, \
    Checkbox, \
    Form, \
    InvalidValueFormat


class Web2LDAPForm(Form):
    """
    Form sub-class for a web2ldap use-case

    more sub-classes define forms for different URL commands
    """
    command = None
    cookie_length = web2ldapcnf.cookie_length or 2 * 42
    cookie_max_age = web2ldapcnf.cookie_max_age
    cookie_domain = web2ldapcnf.cookie_domain
    cookie_name_prefix = 'web2ldap_'

    def __init__(self, inf, env):
        Form.__init__(self, inf, env)
        # Cookie handling
        try:
            self.cookies = http.cookies.SimpleCookie(self.env['HTTP_COOKIE'])
        except KeyError:
            self.cookies = http.cookies.SimpleCookie()
        self.next_cookie = http.cookies.SimpleCookie()

    def utf2display(
            self,
            value,
            tab_identiation='',
            sp_entity='&nbsp;&nbsp;',
            lf_entity='\n'
        ):
        assert isinstance(value, str), \
            TypeError('Argument value must be str, was %r' % (value,))
        value = value or u''
        return escape_html(value).replace('\n', lf_entity).replace('\t', tab_identiation).replace('  ', sp_entity)

    def unset_cookie(self, cki):
        if cki is not None:
            assert len(cki) == 1, \
                ValueError(
                    'More than one Morsel cookie instance in cki: %d objects found' % (len(cki))
                )
            cookie_name = list(cki.keys())[0]
            cki[cookie_name] = ''
            cki[cookie_name]['max-age'] = 0
            self.next_cookie.update(cki)
        # end of unset_cookie()

    def get_cookie_domain(self):
        if self.cookie_domain:
            cookie_domain = self.cookie_domain
        elif 'SERVER_NAME' in self.env or 'HTTP_HOST' in self.env:
            cookie_domain = self.env.get('HTTP_HOST', self.env['SERVER_NAME']).split(':')[0]
        return cookie_domain

    def set_cookie(self, name_suffix):
        # Generate a randomized key and value
        cookie_key = random_string(
            alphabet=web2ldap.web.session.SESSION_ID_CHARS,
            length=self.cookie_length,
        )
        cookie_name = ''.join((self.cookie_name_prefix, name_suffix))
        cki = http.cookies.SimpleCookie({
            cookie_name: cookie_key,
        })
        cki[cookie_name]['path'] = self.script_name
        cki[cookie_name]['domain'] = self.get_cookie_domain()
        cki[cookie_name]['max-age'] = str(self.cookie_max_age)
        cki[cookie_name]['httponly'] = None
        if self.env.get('HTTPS', None) == 'on':
            cki[cookie_name]['secure'] = None
        self.next_cookie.update(cki)
        return cki # set_cookie()

    def fields(self):
        return [
            Input(
                'delsid',
                u'Old SID to be deleted',
                session_store.session_id_len,
                1,
                session_store.session_id_re.pattern
            ),
            Input('who', u'Bind DN/AuthcID', 1000, 1, u'.*', size=40),
            Input('cred', u'with Password', 200, 1, u'.*', size=15),
            Select(
                'login_authzid_prefix',
                u'SASL AuthzID',
                1,
                options=[(u'', u'- no prefix -'), ('u:', u'user-ID'), ('dn:', u'DN')],
                default=None
            ),
            Input('login_authzid', u'SASL AuthzID', 1000, 1, u'.*', size=20),
            Input('login_realm', u'SASL Realm', 1000, 1, u'.*', size=20),
            AuthMechSelect('login_mech', u'Authentication mechanism'),
            Input('ldapurl', u'LDAP Url', 1024, 1, '[ ]*ldap(|i|s)://.*', size=30),
            Input(
                'host', u'Host:Port',
                255, 1,
                '(%s|[a-zA-Z0-9/._-]+)' % web2ldap.app.gui.host_pattern,
                size=30,
            ),
            DistinguishedNameInput('dn', 'Distinguished Name'),
            Select(
                'scope', 'Scope', 1,
                options=web2ldap.app.searchform.SEARCH_SCOPE_OPTIONS,
                default=web2ldap.app.searchform.SEARCH_SCOPE_STR_SUBTREE,
            ),
            DistinguishedNameInput('login_search_root', 'Login search root'),
            Select(
                'conntype', 'Connection type', 1,
                options=[
                    (u'0', u'LDAP clear-text connection'),
                    (u'1', u'LDAP with StartTLS ext.op.'),
                    (u'2', u'LDAP over separate SSL port (LDAPS)'),
                    (u'3', u'LDAP over Unix domain socket (LDAPI)')
                ],
                default=u'0',
            )
        ]

    def action_url(self, command, sid):
        return '%s/%s%s' % (
            self.script_name,
            command,
            {False:'/%s' % sid, True:''}[sid is None],
        )

    def begin_form(
            self,
            command,
            sid,
            method,
            target=None,
            enctype='application/x-www-form-urlencoded',
        ):
        target = {
            False:'target="%s"' % (target),
            True:'',
        }[target is None]
        return """
          <form
            action="%s"
            method="%s"
            %s
            enctype="%s"
            accept-charset="%s"
          >
          """  % (
              self.action_url(command, sid),
              method,
              target,
              enctype,
              self.accept_charset
          )

    def hiddenFieldHTML(self, name, value, desc):
        return web2ldap.app.gui.HIDDEN_FIELD % (
            name,
            self.utf2display(value, sp_entity='  '),
            self.utf2display(desc, sp_entity='&nbsp;&nbsp;'),
        )

    def hiddenInputHTML(self, ignoreFieldNames=None):
        """
        Return all input parameters as hidden fields in one HTML string.

        ignoreFieldNames
            Names of parameters to be excluded.
        """
        ignoreFieldNames = set(ignoreFieldNames or [])
        result = []
        for f in [
                self.field[p]
                for p in self.input_field_names
                if not p in ignoreFieldNames
            ]:
            for val in f.value:
                if not isinstance(val, str):
                    val = self.uc_decode(val)[0]
                result.append(self.hiddenFieldHTML(f.name, val, u''))
        return '\n'.join(result) # hiddenInputFieldString()


class SearchAttrs(Input):

    def __init__(self, name='search_attrs', text=u'Attributes to be read'):
        Input.__init__(self, name, text, 1000, 1, u'[@*+0-9.\\w,_;-]+')

    def set_value(self, value):
        value = ','.join(
            filter(
                None,
                map(str.strip, value.replace(' ', ',').split(','))
            )
        )
        Input.set_value(self, value)


class Web2LDAPForm_searchform(Web2LDAPForm):
    command = 'searchform'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Input(
                'search_submit', u'Search form submit button',
                6, 1,
                '(Search|[+-][0-9]+)',
            ),
            Select(
                'searchform_mode',
                u'Search form mode',
                1,
                options=[(u'base', u'Base'), (u'adv', u'Advanced'), (u'exp', u'Expert')],
                default=u'base',
            ),
            DistinguishedNameInput('search_root', 'Search root'),
            Input(
                'filterstr',
                u'Search filter string',
                1200,
                1,
                '.*',
                size=90,
            ),
            Input(
                'searchform_template',
                u'Search form template name',
                60,
                web2ldapcnf.max_searchparams,
                u'[a-zA-Z0-9. ()_-]+',
            ),
            Select(
                'search_resnumber', u'Number of results to display', 1,
                options=[
                    (u'0', u'unlimited'), (u'10', u'10'), (u'20', u'20'),
                    (u'50', u'50'), (u'100', u'100'), (u'200', u'200'),
                ],
                default=u'10'
            ),
            Select(
                'search_lastmod', u'Interval of last creation/modification', 1,
                options=[
                    (u'-1', u'-'),
                    (u'10', u'10 sec.'),
                    (u'60', u'1 min.'),
                    (u'600', u'10 min.'),
                    (u'3600', u'1 hour'),
                    (u'14400', u'4 hours'),
                    (u'43200', u'12 hours'),
                    (u'86400', u'24 hours'),
                    (u'172800', u'2 days'),
                    (u'604800', u'1 week'),
                    (u'2419200', u'4 weeks'),
                    (u'6048000', u'10 weeks'),
                    (u'31536000', u'1 year'),
                ],
                default=u'-1'
            ),
            InclOpAttrsCheckbox(default=u'yes', checked=False),
            Select('search_mode', u'Search Mode', 1, options=[u'(&%s)', u'(|%s)']),
            Input(
                'search_attr',
                u'Attribute(s) to be searched',
                100,
                web2ldapcnf.max_searchparams,
                u'[\\w,_;-]+',
            ),
            Input(
                'search_mr', u'Matching Rule',
                100,
                web2ldapcnf.max_searchparams,
                u'[\\w,_;-]+',
            ),
            Select(
                'search_option', u'Search option',
                web2ldapcnf.max_searchparams,
                options=web2ldap.app.searchform.search_options,
            ),
            Input(
                'search_string', u'Search string',
                600,
                web2ldapcnf.max_searchparams,
                u'.*',
                size=60,
            ),
            SearchAttrs(),
            ExportFormatSelect(),
        ])
        return res


class Web2LDAPForm_search(Web2LDAPForm_searchform):
    command = 'search'

    def fields(self):
        res = Web2LDAPForm_searchform.fields(self)
        res.extend([
            Input(
                'search_resminindex',
                u'Minimum index of search results',
                10, 1,
                u'[0-9]+',
            ),
            Input(
                'search_resnumber',
                u'Number of results to display',
                3, 1,
                u'[0-9]+',
            ),
        ])
        return res


class Web2LDAPForm_conninfo(Web2LDAPForm):
    command = 'conninfo'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.append(
            Select(
                'conninfo_flushcaches',
                u'Flush caches',
                1,
                options=(u'0', u'1'),
                default=u'0',
            )
        )
        return res


class Web2LDAPForm_params(Web2LDAPForm):
    command = 'params'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Select(
                'params_all_controls',
                u'List all controls',
                1,
                options=(u'0', u'1'),
                default=u'0',
            ),
            Input(
                'params_enable_control',
                u'Enable LDAPv3 Boolean Control',
                50, 1,
                u'([0-9]+.)*[0-9]+',
            ),
            Input(
                'params_disable_control',
                u'Disable LDAPv3 Boolean Control',
                50, 1,
                u'([0-9]+.)*[0-9]+',
            ),
            Select(
                'ldap_deref',
                u'Dereference aliases',
                maxValues=1,
                default=str(ldap0.DEREF_NEVER),
                options=[
                    (str(ldap0.DEREF_NEVER), u'never'),
                    (str(ldap0.DEREF_SEARCHING), u'searching'),
                    (str(ldap0.DEREF_FINDING), u'finding'),
                    (str(ldap0.DEREF_ALWAYS), u'always'),
                ]
            ),
        ])
        return res


class Web2LDAPForm_input(Web2LDAPForm):

    """Base class for entry data input not directly used"""
    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Input('in_oc', u'Object classes', 60, 40, u'[a-zA-Z0-9.-]+'),
            Select(
                'in_ft', u'Type of input form',
                1,
                options=(u'Template', u'Table', u'LDIF', u'OC'),
                default=u'Template',
            ),
            Input(
                'in_mr',
                u'Add/del row',
                8, 1,
                '(Template|Table|LDIF|[+-][0-9]+)',
            ),
            Select(
                'in_oft', u'Type of input form',
                1,
                options=(u'Template', u'Table', u'LDIF'),
                default=u'Template',
            ),
            AttributeType('in_at', u'Attribute type', web2ldapcnf.input_maxattrs),
            AttributeType('in_avi', u'Value index', web2ldapcnf.input_maxattrs),
            BytesInput(
                'in_av', u'Attribute Value',
                web2ldapcnf.input_maxfieldlen,
                web2ldapcnf.input_maxattrs,
                None
            ),
            LDIFTextArea('in_ldif', u'LDIF data'),
            Select(
                'in_ocf', u'Object class form mode', 1,
                options=[
                    (u'tmpl', u'LDIF templates'),
                    (u'exp', u'Object class selection')
                ],
                default=u'tmpl',
            ),
        ])
        return res


class Web2LDAPForm_add(Web2LDAPForm_input):
    command = 'add'

    def fields(self):
        res = Web2LDAPForm_input.fields(self)
        res.extend([
            Input('add_rdn', u'RDN of new entry', 255, 1, u'.*', size=50),
            DistinguishedNameInput('add_clonedn', u'DN of template entry'),
            Input(
                'add_template', u'LDIF template name',
                60,
                web2ldapcnf.max_searchparams,
                u'.+',
            ),
            Input('add_basedn', u'Base DN of new entry', 1024, 1, u'.*', size=50),
        ])
        return res


class Web2LDAPForm_modify(Web2LDAPForm_input):
    command = 'modify'

    def fields(self):
        res = Web2LDAPForm_input.fields(self)
        res.extend([
            AttributeType(
                'in_oldattrtypes',
                u'Old attribute types',
                web2ldapcnf.input_maxattrs,
            ),
            AttributeType(
                'in_wrtattroids',
                u'Writeable attribute types',
                web2ldapcnf.input_maxattrs,
            ),
            Input(
                'in_assertion',
                u'Assertion filter string',
                2000,
                1,
                '.*',
                required=False,
            ),
        ])
        return res


class Web2LDAPForm_dds(Web2LDAPForm):
    command = 'dds'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Input(
                'dds_renewttlnum',
                u'Request TTL number',
                12, 1,
                '[0-9]+',
                default=None,
            ),
            Select(
                'dds_renewttlfac',
                u'Request TTL factor',
                1,
                options=(
                    (u'1', u'seconds'),
                    (u'60', u'minutes'),
                    (u'3600', u'hours'),
                    (u'86400', u'days'),
                ),
                default=u'1'
            ),
        ])
        return res


class Web2LDAPForm_bulkmod(Web2LDAPForm):
    command = 'bulkmod'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        bulkmod_ctrl_options = [
            (control_oid, OID_REG.get(control_oid, (control_oid,))[0])
            for control_oid, control_spec in AVAILABLE_BOOLEAN_CONTROLS.items()
            if (
                '**all**' in control_spec[0]
                or '**write**' in control_spec[0]
                or 'modify' in control_spec[0]
            )
        ]
        res.extend([
            Input(
                'bulkmod_submit',
                u'Search form submit button',
                6, 1,
                u'(Next>>|<<Back|Apply|Cancel|[+-][0-9]+)',
            ),
            Select(
                'bulkmod_ctrl',
                u'Extended controls',
                len(bulkmod_ctrl_options),
                options=bulkmod_ctrl_options,
                default=None,
                size=min(8, len(bulkmod_ctrl_options)),
                multiSelect=1,
            ),
            Input(
                'filterstr',
                u'Search filter string for searching entries to be deleted',
                1200, 1,
                '.*',
            ),
            Input(
                'bulkmod_modrow',
                u'Add/del row',
                8, 1,
                '(Template|Table|LDIF|[+-][0-9]+)',
            ),
            AttributeType('bulkmod_at', u'Attribute type', web2ldapcnf.input_maxattrs),
            Select(
                'bulkmod_op',
                u'Modification type',
                web2ldapcnf.input_maxattrs,
                options=(
                    (u'', u''),
                    (str(ldap0.MOD_ADD), u'add'),
                    (str(ldap0.MOD_DELETE), u'delete'),
                    (str(ldap0.MOD_REPLACE), u'replace'),
                    (str(ldap0.MOD_INCREMENT), u'increment'),
                ),
                default=None,
            ),
            BytesInput(
                'bulkmod_av', u'Attribute Value',
                web2ldapcnf.input_maxfieldlen,
                web2ldapcnf.input_maxattrs,
                None,
                size=30,
            ),
            DistinguishedNameInput('bulkmod_newsuperior', u'New superior DN'),
            Checkbox('bulkmod_cp', u'Copy entries', 1, default=u'yes', checked=False),
        ])
        return res


class Web2LDAPForm_delete(Web2LDAPForm):
    command = 'delete'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        delete_ctrl_options = [
            (control_oid, OID_REG.get(control_oid, (control_oid,))[0])
            for control_oid, control_spec in AVAILABLE_BOOLEAN_CONTROLS.items()
            if (
                '**all**' in control_spec[0]
                or '**write**' in control_spec[0]
                or 'delete' in control_spec[0]
            )
        ]
        delete_ctrl_options.append((web2ldap.ldapsession.CONTROL_TREEDELETE, u'Tree Deletion'))
        res.extend([
            Select(
                'delete_confirm', u'Confirmation',
                1,
                options=('yes', 'no'),
                default=u'no',
            ),
            Select(
                'delete_ctrl',
                u'Extended controls',
                len(delete_ctrl_options),
                options=delete_ctrl_options,
                default=None,
                size=min(8, len(delete_ctrl_options)),
                multiSelect=1,
            ),
            Input(
                'filterstr',
                u'Search filter string for searching entries to be deleted',
                1200, 1,
                '.*',
            ),
            Input('delete_attr', u'Attribute to be deleted', 255, 100, u'[\\w_;-]+'),
        ])
        return res


class Web2LDAPForm_rename(Web2LDAPForm):
    command = 'rename'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Input(
                'rename_newrdn',
                u'New RDN',
                255, 1,
                web2ldap.ldaputil.rdn_pattern,
                size=50,
            ),
            DistinguishedNameInput('rename_newsuperior', u'New superior DN'),
            Checkbox('rename_delold', u'Delete old', 1, default=u'yes', checked=True),
            Input(
                'rename_newsupfilter',
                u'Filter string for searching new superior entry', 300, 1, '.*',
                default=u'(|(objectClass=organization)(objectClass=organizationalUnit))',
                size=50,
            ),
            DistinguishedNameInput(
                'rename_searchroot',
                u'Search root under which to look for new superior entry.',
            ),
            Input(
                'rename_supsearchurl',
                u'LDAP URL for searching new superior entry',
                100, 1,
                '.*',
                size=30,
            ),
        ])
        return res


class Web2LDAPForm_passwd(Web2LDAPForm):
    command = 'passwd'
    passwd_actions = (
        (
            'passwdextop',
            'Server-side',
            u'Password modify extended operation',
        ),
        (
            'setuserpassword',
            'Modify password attribute',
            u'Set the password attribute with modify operation'
        ),
    )

    @staticmethod
    def passwd_fields():
        """
        return list of Field instances needed for a password change input form
        """
        return [
            Select(
                'passwd_action', u'Password action', 1,
                options=[
                    (action, short_desc)
                    for action, short_desc, _ in Web2LDAPForm_passwd.passwd_actions
                ],
                default=u'setuserpassword'
            ),
            DistinguishedNameInput('passwd_who', u'Password DN'),
            Field('passwd_oldpasswd', u'Old password', 100, 1, '.*'),
            Field('passwd_newpasswd', u'New password', 100, 2, '.*'),
            Select(
                'passwd_scheme', u'Password hash scheme', 1,
                options=web2ldap.ldaputil.passwd.AVAIL_USERPASSWORD_SCHEMES.items(),
                default=None,
            ),
            Checkbox(
                'passwd_ntpasswordsync',
                u'Sync ntPassword for Samba',
                1,
                default=u'yes',
                checked=True,
            ),
            Checkbox(
                'passwd_settimesync',
                u'Sync password setting times',
                1,
                default=u'yes',
                checked=True,
            ),
            Checkbox(
                'passwd_forcechange',
                u'Force password change',
                1,
                default=u'yes',
                checked=False,
            ),
            Checkbox(
                'passwd_inform',
                u'Password change inform action',
                1,
                default="display_url",
                checked=False,
            ),
        ]

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend(self.passwd_fields())
        return res


class Web2LDAPForm_read(Web2LDAPForm):
    command = 'read'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            Input(
                'filterstr',
                u'Search filter string when reading single entry',
                1200, 1,
                '.*',
            ),
            Select(
                'read_nocache', u'Force fresh read',
                1,
                options=[u'0', u'1'],
                default=u'0',
            ),
            Input('read_attr', u'Read attribute', 255, 100, u'[\\w_;-]+'),
            Input('read_attrindex', u'Read attribute', 255, 1, u'[0-9]+'),
            Input('read_attrmimetype', u'MIME type', 255, 1, u'[\\w.-]+/[\\w.-]+'),
            Select(
                'read_output', u'Read output format',
                1,
                options=(u'table', u'vcard', u'template'),
                default=u'template',
            ),
            SearchAttrs(),
            Input('read_expandattr', u'Attributes to be read', 1000, 50, u'[*+\\w,_;-]+'),
        ])
        return res


class Web2LDAPForm_groupadm(Web2LDAPForm):
    command = 'groupadm'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            DistinguishedNameInput('groupadm_searchroot', u'Group search root'),
            Input('groupadm_name', u'Group name', 100, 1, u'.*', size=30),
            DistinguishedNameInput('groupadm_add', u'Add to group', 300),
            DistinguishedNameInput('groupadm_remove', u'Remove from group', 300),
            Select(
                'groupadm_view',
                u'Group list view',
                1,
                options=(
                    ('0', 'none of the'),
                    ('1', 'only member'),
                    ('2', 'all'),
                ),
                default=u'1',
            ),
        ])
        return res


class Web2LDAPForm_login(Web2LDAPForm):
    command = 'login'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.append(
            DistinguishedNameInput('login_who', u'Bind DN')
        )
        return res


class Web2LDAPForm_locate(Web2LDAPForm):
    command = 'locate'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.append(
            Input('locate_name', u'Location name', 500, 1, u'.*', size=25)
        )
        return res


class Web2LDAPForm_oid(Web2LDAPForm):
    command = 'oid'

    def fields(self):
        res = Web2LDAPForm.fields(self)
        res.extend([
            OIDInput('oid', u'OID'),
            Select(
                'oid_class',
                u'Schema element class',
                1,
                options=ldap0.schema.SCHEMA_ATTRS,
                default=u'',
            ),
        ])
        return res


class Web2LDAPForm_dit(Web2LDAPForm):
    command = 'dit'


class DistinguishedNameInput(Input):
    """Input field class for LDAP DNs."""

    def __init__(self, name='dn', text='DN', maxValues=1, required=False, default=u''):
        Input.__init__(
            self, name, text, 1024, maxValues, None,
            size=70, required=required, default=default
        )

    def _validate_format(self, value):
        if value and not ldap0.dn.is_dn(value):
            raise InvalidValueFormat(
                self.name,
                self.text.encode(self.charset),
                value.encode(self.charset)
            )


class LDIFTextArea(Textarea):
    """A single multi-line input field for LDIF data"""

    def __init__(
            self,
            name='in_ldif',
            text='LDIF data',
            required=False,
            max_entries=1
        ):
        Textarea.__init__(
            self,
            name,
            text,
            web2ldapcnf.ldif_maxbytes,
            1,
            '^.*$',
            required=required,
        )
        self._max_entries = max_entries
        self.allRecords = []

    def getLDIFRecords(self):
        if self.value:
            return list(
                ldap0.ldif.LDIFParser.frombuf(
                    '\n'.join(self.value).encode(self.charset),
                    ignored_attr_types=[],
                    process_url_schemes=web2ldapcnf.ldif_url_schemes
                ).parse(max_entries=self._max_entries)
            )
        return []


class OIDInput(Input):

    def __init__(self, name, text, default=None):
        Input.__init__(
            self, name, text,
            512, 1, u'[a-zA-Z0-9_.;*-]+',
            default=default,
            required=False,
            size=30,
        )


class ObjectClassSelect(Select):
    """Select field class for choosing the object class(es)"""

    def __init__(
            self,
            name='in_oc',
            text='Object classes',
            options=None,
            default=None,
            required=False,
            accesskey='',
            size=12, # Size of displayed select field
        ):
        select_default = default or []
        select_default.sort(key=str.lower)
        additional_options = [
            opt
            for opt in options or []
            if not opt in select_default
        ]
        additional_options.sort(key=str.lower)
        select_options = select_default[:]
        select_options.extend(additional_options)
        Select.__init__(
            self,
            name, text,
            maxValues=200,
            required=required,
            options=select_options,
            default=select_default,
            accesskey=accesskey,
            size=size,
            ignoreCase=1,
            multiSelect=1
        )
        self.setRegex(u'[\\w]+')
        self.maxLen = 200
        # end of ObjectClassSelect()


class ExportFormatSelect(Select):
    """Select field class for choosing export format"""

    def __init__(
            self,
            default=u'ldif1',
            required=False,
        ):
        Select.__init__(
            self,
            'search_output',
            u'Export format',
            1,
            options=(
                (u'table', u'Table/template'),
                (u'raw', u'Raw DN list'),
                (u'print', u'Printable'),
                (u'ldif', u'LDIF (Umich)'),
                (u'ldif1', u'LDIFv1 (RFC2849)'),
                (u'csv', u'CSV'),
                (u'excel', u'Excel'),
            ),
            default=default,
            required=required,
            size=1,
        )


class AttributeType(Input):
    """
    Input field for an LDAP attribute type
    """
    def __init__(self, name, text, maxValues):
        Input.__init__(
            self,
            name,
            text,
            500,
            maxValues,
            web2ldap.ldaputil.attr_type_pattern,
            required=False,
            size=30
        )


class InclOpAttrsCheckbox(Checkbox):

    def __init__(self, default=u'yes', checked=False):
        Checkbox.__init__(
            self,
            'search_opattrs',
            u'Request operational attributes',
            1,
            default=default,
            checked=checked
        )


class AuthMechSelect(Select):
    """Select field class for choosing the bind mech"""

    supported_bind_mechs = {
        u'': u'Simple Bind',
        u'DIGEST-MD5': u'SASL Bind: DIGEST-MD5',
        u'CRAM-MD5': u'SASL Bind: CRAM-MD5',
        u'PLAIN': u'SASL Bind: PLAIN',
        u'LOGIN': u'SASL Bind: LOGIN',
        u'GSSAPI': u'SASL Bind: GSSAPI',
        u'EXTERNAL': u'SASL Bind: EXTERNAL',
        u'OTP': u'SASL Bind: OTP',
        u'NTLM': u'SASL Bind: NTLM',
        u'SCRAM-SHA-1': u'SASL Bind: SCRAM-SHA-1',
        u'SCRAM-SHA-256': u'SASL Bind: SCRAM-SHA-256',
    }

    def __init__(
            self,
            name='login_mech',
            text=u'Authentication mechanism',
            default=None,
            required=False,
            accesskey='',
            size=1,
        ):
        Select.__init__(
            self,
            name, text, maxValues=1,
            required=required,
            options=None,
            default=default or [],
            accesskey=accesskey,
            size=size,
            ignoreCase=0,
            multiSelect=0
        )

    def setOptions(self, options):
        options_dict = {}
        options_dict[u''] = self.supported_bind_mechs[u'']
        for o in options or self.supported_bind_mechs.keys():
            o_upper = o.upper()
            if o_upper in self.supported_bind_mechs:
                options_dict[o_upper] = self.supported_bind_mechs[o_upper]
        Select.setOptions(self, options_dict.items())
