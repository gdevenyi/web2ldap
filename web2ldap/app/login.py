# -*- coding: utf-8 -*-
"""
web2ldap.app.login: bind with a specific bind DN and password

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2019 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

import time

import web2ldap.app.core
import web2ldap.app.gui
import web2ldap.app.cnf
from web2ldap.log import logger


def w2l_login(
        app,
        title_msg=u'Bind',
        login_msg='',
        who=u'',
        relogin=False,
        nomenu=False,
        login_default_mech=None
    ):
    """
    Provide a input form for doing a (re-)login
    """

    login_search_root = app.form.getInputValue(
        'login_search_root',
        [app.naming_context or app.dn or u''],
    )[0]

    if 'login_who' in app.form.input_field_names:
        who = app.form.field['login_who'].value[0]

    login_search_root = login_search_root or app.dn

    login_search_root_field = web2ldap.app.gui.search_root_field(
        app,
        name='login_search_root',
    )
    login_search_root_field.set_default(str(login_search_root))

    login_template_str = web2ldap.app.gui.read_template(app, 'login_template', u'login form')

    if nomenu:
        main_menu_list = []
    else:
        main_menu_list = web2ldap.app.gui.main_menu(app)

    web2ldap.app.gui.top_section(
        app,
        login_msg,
        main_menu_list,
        context_menu_list=[],
        main_div_id='Input',
    )

    if app.ls.rootDSE:
        app.form.field['login_mech'].setOptions(app.ls.supportedSASLMechanisms or [])

    # Determine the bind mech to be used from the
    # form data or the key-word argument login_default_mech
    login_mech = app.form.getInputValue('login_mech', [login_default_mech] or u'')[0]

    login_fields = login_template_str.format(
        field_login_mech=app.form.field['login_mech'].input_html(default=login_mech),
        value_ldap_who=app.form.utf2display(who or u''),
        value_ldap_mapping=app.form.utf2display(app.binddn_mapping),
        field_login_search_root=login_search_root_field.input_html(),
        field_login_authzid_prefix=app.form.field['login_authzid_prefix'].input_html(),
        value_submit={False:'Login', True:'Retry w/login'}[relogin],
        value_currenttime=time.strftime(r'%Y%m%d%H%M%SZ', time.gmtime()),
    )

    scope_str = app.form.getInputValue('scope', [None])[0]
    if not scope_str and app.ldap_url.scope is not None:
        scope_str = str(app.ldap_url.scope)
    if scope_str:
        scope_hidden_field = app.form.hiddenFieldHTML('scope', scope_str, u'')
    else:
        scope_hidden_field = ''

    if 'filterstr' in app.form.field:
        filterstr = app.form.getInputValue(
            'filterstr',
            [app.ldap_url.filterstr or ''],
        )[0]
    else:
        filterstr = app.ldap_url.filterstr or ''
    if filterstr:
        filterstr_hidden_field = app.form.hiddenFieldHTML('filterstr', filterstr, u'')
    else:
        filterstr_hidden_field = ''

    search_attrs_hidden_field = ''
    if app.command in {'search', 'searchform'}:
        search_attrs = app.form.getInputValue('search_attrs', [u','.join(app.ldap_url.attrs or [])])[0]
        if search_attrs:
            search_attrs_hidden_field = app.form.hiddenFieldHTML('search_attrs', search_attrs, u'')

    if login_msg:
        login_msg_html = '<p class="ErrorMessage">%s</p>' % (login_msg)
    else:
        login_msg_html = ''

    # determine which command will be put in form's action attribute
    if not app.command or app.command == 'login':
        action_command = 'searchform'
    else:
        action_command = app.command

    logger.debug('Display login form for %r with next command %r', app.dn, action_command)

    app.outf.write(
        '<h1>%s</h1>\n%s' % (
            app.form.utf2display(title_msg),
            '\n'.join((
                login_msg_html,
                app.form.begin_form(action_command, None, 'POST', None),
                app.form.hiddenFieldHTML('ldapurl', str(app.ls.ldapUrl('')), u''),
                app.form.hiddenFieldHTML('dn', app.dn, u''),
                app.form.hiddenFieldHTML('delsid', app.sid, u''),
                app.form.hiddenFieldHTML('conntype', str(int(app.ls.startTLSOption > 0)), u''),
                scope_hidden_field,
                filterstr_hidden_field,
                login_fields,
                search_attrs_hidden_field,
            ))
        )
    )
    if relogin:
        app.outf.write(
            app.form.hiddenInputHTML(
                ignoreFieldNames=set([
                    'sid', 'delsid',
                    'ldapurl', 'conntype', 'host', 'who', 'cred',
                    'dn', 'scope', 'filterstr', 'search_attrs',
                    'login_mech', 'login_authzid', 'login_authzid_prefix', 'login_realm',
                    'login_search_root',
                ])
            )
        )
    app.outf.write('</form>\n')
    web2ldap.app.gui.footer(app)
