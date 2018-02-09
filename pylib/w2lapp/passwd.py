# -*- coding: utf-8 -*-
"""
w2lapp.passwd: change password associated with entry

web2ldap - a web-based LDAP Client,
see http://www.web2ldap.de for details

(c) by Michael Stroeder <michael@stroeder.com>

This module is distributed under the terms of the
GPL (GNU GENERAL PUBLIC LICENSE) Version 2
(see http://www.gnu.org/copyleft/gpl.html)
"""

from __future__ import absolute_import

import time,string,binascii,hashlib,ldap0,ldaputil.base,ldaputil.passwd, \
       ldapsession,w2lapp.cnf,w2lapp.core,w2lapp.gui,w2lapp.login

from ldaputil.passwd import RandomString

available_hashtypes = ldaputil.passwd.AVAIL_USERPASSWORD_SCHEMES.items()


PASSWD_ACTIONS = [
  (u'passwdextop',u'Server-side',u'Password modify extended operation'),
  (u'setuserpassword',u'Modify password attribute',u'Set the password attribute with modify operation'),
]
PASSWD_ACTIONS_DICT = dict([
  (action,(short_desc,long_desc))
  for action,short_desc,long_desc in PASSWD_ACTIONS
])

PASSWD_GEN_LENGTH = 20
PASSWD_GEN_CHARS = unicode(string.ascii_lowercase+string.digits+'./\<>!"$','utf-8')


def NtPasswordHash(password):
  """
  Returns MD4-based NT password hash for a password.
  """
  md4_digest = hashlib.new('md4')
  md4_digest.update(password[:128].encode('utf-16-le'))
  return binascii.hexlify(md4_digest.digest()).upper()


def GetAllAllowedAttributes(schema,oc_list):
  r,a = schema.attribute_types(oc_list,raise_keyerror=0)
  result = {}
  result.update(r)
  result.update(a)
  return result # GetAllAllowedAttributes()


def PasswordChangeUrl(form,ls,passwd_who,passwd_input):
  passwd_who_ldapurl_obj = ls.ldapUrl(passwd_who)
  passwd_who_ldapurl_obj.scope = ldap0.SCOPE_BASE
  passwd_who_ldapurl_obj.who = passwd_who.encode(ls.charset)
  passwd_who_ldapurl_obj.cred = passwd_input.encode(ls.charset)
  passwd_who_ldapurl_obj.cred = passwd_input.encode(ls.charset)
  passwd_who_ldapurl_obj.saslMech = None
  return '?'.join((
    form.actionUrlHTML('passwd',None),
    str(passwd_who_ldapurl_obj),
  ))


def PasswdContextMenu(sid,form,dn,sub_schema):
  result = [
    form.applAnchor(
      'passwd',
      short_desc,sid,
      [
        ('dn',dn),
        ('passwd_action',pa),
        ('passwd_who',dn),
      ],
      title=long_desc
    )
    for pa,short_desc,long_desc in PASSWD_ACTIONS
  ]
  # Menu entry for unlocking entry
  delete_param_list = [
    ('dn',dn),
    ('delete_ctrl',ldapsession.CONTROL_RELAXRULES),
  ]
  delete_param_list.extend([
    ('delete_attr',attr_type)
    for attr_type in (
      # Samba-Passwortattribute
      u'sambaBadPasswordCount',u'sambaBadPasswordTime',
      # draft-behera-ldap-password-policy
      u'pwdAccountLockedTime',u'pwdFailureTime',
      # SunONE/Netscape/Fedora/389 Directory Server
      u'passwordRetryCount',u'accountUnlockTime',
    )
    if sub_schema.get_obj(ldap0.schema.models.AttributeType,attr_type.encode('ascii'),None)!=None
  ])
  result.append(
    form.applAnchor(
      'delete','Unlock',
      sid,delete_param_list,
      title=u'Unlock locked out entry'
    )
  )
  # Menu entry for deleting all password-related attrs
  delete_param_list = [('dn',dn)]
  delete_param_list.extend([
    ('delete_attr',attr_type)
    for attr_type in (
      u'userPassword',
      # Samba-Passwortattribute
      u'sambaBadPasswordCount',u'sambaBadPasswordTime',u'sambaClearTextPassword',
      u'sambaLMPassword',u'sambaNTPassword',u'sambaPasswordHistory',
      u'sambaPreviousClearTextPassword',
      # draft-behera-ldap-password-policy
      u'pwdAccountLockedTime',u'pwdHistory',u'pwdChangedTime',u'pwdFailureTime',
      u'pwdReset',u'pwdPolicySubentry',u'pwdGraceUseTime',
      u'pwdStartTime',u'pwdEndTime',u'pwdLastSuccess',
      # OpenDJ
      u'ds-pwp-password-policy-dn',
      # SunONE/Netscape/Fedora/389 Directory Server
      u'passwordExpirationTime',u'passwordExpWarned',
      u'passwordRetryCount',u'accountUnlockTime',u'retryCountResetTime',
    )
    if sub_schema.get_obj(ldap0.schema.models.AttributeType,attr_type.encode('ascii'),None)!=None
  ])
  result.append(
    form.applAnchor(
      'delete','Unset',
      sid,delete_param_list,
      title=u'Delete password related attributes'
    )
  )
  return result


def OwnPwdChange(ls,dn):
  return (ls.who is None) or (ls.who==dn)


def PasswdForm(
  sid,outf,form,ls,dn,sub_schema,
  passwd_action,passwd_who,user_objectclasses,
  Heading,Msg
):

  sub_schema = ls.retrieveSubSchema(
    dn,
    w2lapp.cnf.GetParam(ls,'_schema',None),
    w2lapp.cnf.GetParam(ls,'supplement_schema',None),
    w2lapp.cnf.GetParam(ls,'schema_strictcheck',True),
  )

  if not user_objectclasses:
    try:
      user_objectclasses = [ oc.lower() for oc in ls.getObjectClasses(passwd_who)[0] ]
    except (
        ldap0.CONSTRAINT_VIOLATION,
        ldap0.INSUFFICIENT_ACCESS,
    ):
      user_objectclasses = []

  if Msg:
    Msg = '<p class="ErrorMessage">%s</p>' % (Msg)

  # Determine whether password attribute is unicodePwd on MS AD
  unicode_pwd_avail = sub_schema.sed[ldap0.schema.models.AttributeType].has_key('1.2.840.113556.1.4.90')

  # Determine whether user changes own password
  own_pwd_change = OwnPwdChange(ls,passwd_who)

  all_attrs_dict = GetAllAllowedAttributes(sub_schema,user_objectclasses)

  if not unicode_pwd_avail:

  #  config_hashtypes = ls.rootDSE.get('supportedAuthPasswordSchemes',None) or w2lapp.cnf.GetParam(ls,'passwd_hashtypes',[])
    config_hashtypes = w2lapp.cnf.GetParam(ls,'passwd_hashtypes',[])
    if config_hashtypes:
      # The set of hash types are restricted by local configuration
      default_hashtypes = [
        hash_type
        for hash_type in available_hashtypes
        if hash_type[0] in config_hashtypes
      ]
      form.field['passwd_scheme'].options = default_hashtypes

  nthash_available = all_attrs_dict.has_key('1.3.6.1.4.1.7165.2.1.25')
  show_clientside_pw_fields = passwd_action=='setuserpassword' and not unicode_pwd_avail

  passwd_template_str = w2lapp.gui.ReadTemplate(form,ls,'passwd_template',u'password form')

  w2lapp.gui.TopSection(
    sid,outf,'passwd',form,ls,dn,'Change password',
    w2lapp.gui.MainMenu(sid,form,ls,dn),
    context_menu_list=PasswdContextMenu(sid,form,dn,sub_schema),
    main_div_id='Input'
  )

  outf.write(passwd_template_str.format(
    text_heading=Heading,
    text_msg=Msg or form.utf2display(PASSWD_ACTIONS_DICT[passwd_action][1]),
    form_begin=form.beginFormHTML('passwd',sid,'POST'),
    value_dn=form.hiddenFieldHTML('dn',dn,u''),
    value_passwd_action=form.hiddenFieldHTML('passwd_action',passwd_action,u''),
    value_passwd_who=form.hiddenFieldHTML('passwd_who',passwd_who,u''),
    text_desc={False:'Change password for',True:'Change own password of'}[own_pwd_change],
    text_whoami=w2lapp.gui.WhoAmITemplate(sid,form,ls,dn,passwd_who),
    disable_oldpw_start={0:'',1:'<!--'}[not own_pwd_change],
    disable_oldpw_end={0:'',1:'-->'}[not own_pwd_change],
    disable_ownuser_start={0:'',1:'<!--'}[own_pwd_change],
    disable_ownuser_end={0:'',1:'-->'}[own_pwd_change],
    disable_clientsidehashing_start={0:'',1:'<!--'}[not show_clientside_pw_fields],
    disable_clientsidehashing_end={0:'',1:'-->'}[not show_clientside_pw_fields],
    disable_syncnthash_start={0:'',1:'<!--'}[not (show_clientside_pw_fields and nthash_available)],
    disable_syncnthash_end={0:'',1:'-->'}[not (show_clientside_pw_fields and nthash_available)],
    disable_settimesync_start={0:'',1:'<!--'}[own_pwd_change or not show_clientside_pw_fields],
    disable_settimesync_end={0:'',1:'-->'}[own_pwd_change or not show_clientside_pw_fields],
    form_field_passwd_scheme=form.field['passwd_scheme'].inputHTML(),
    form_field_passwd_ntpasswordsync=form.field['passwd_ntpasswordsync'].inputHTML(),
    form_field_passwd_settimesync=form.field['passwd_settimesync'].inputHTML(checked=(not own_pwd_change)),
  ))

  w2lapp.gui.Footer(outf,form)
  return # PasswdForm()


def w2l_Passwd(sid,outf,command,form,ls,dn,connLDAPUrl):

  sub_schema = ls.retrieveSubSchema(
    dn,
    w2lapp.cnf.GetParam(ls,'_schema',None),
    w2lapp.cnf.GetParam(ls,'supplement_schema',None),
    w2lapp.cnf.GetParam(ls,'schema_strictcheck',True),
  )

  # Determine the default value for passwd_action based on
  # server's visible configuration
  if '1.3.6.1.4.1.4203.1.11.1' in ls.supportedExtension:
    # Password Modify extended operation seems to be announced in rootDSE
    passwd_action_default = u'passwdextop'
  else:
    passwd_action_default = u'setuserpassword'

  passwd_action = form.getInputValue('passwd_action',[None])[0] or passwd_action_default
  passwd_who = form.getInputValue('passwd_who',[dn])[0]

  try:
    user_objectclasses = [ oc.lower() for oc in ls.getObjectClasses(passwd_who)[0] ]
  except (
    ldap0.CONSTRAINT_VIOLATION,
    ldap0.INSUFFICIENT_ACCESS
  ):
    user_objectclasses = []

  if 'passwd_newpasswd' in form.inputFieldNames:

    ####################################################################
    # New password provided => (re)set it in entry
    ####################################################################

    if len(form.field['passwd_newpasswd'].value)!=2:
      raise w2lapp.core.ErrorExit(u'Repeat password!')

    if form.field['passwd_newpasswd'].value[0]!=form.field['passwd_newpasswd'].value[1]:
      PasswdForm(
        sid,outf,form,ls,dn,sub_schema,passwd_action,passwd_who,user_objectclasses,
        Heading='Password Error',Msg='New passwords do not match!'
      )
      return

    old_password = form.getInputValue('passwd_oldpasswd',[None])[0]

    passwd_input = form.field['passwd_newpasswd'].value[0]

    no_passwd_input = not passwd_input
    if no_passwd_input:
      passwd_input = RandomString(
        w2lapp.cnf.GetParam(ls,'passwd_genlength',PASSWD_GEN_LENGTH),
        w2lapp.cnf.GetParam(ls,'passwd_genchars',PASSWD_GEN_CHARS),
      )

    passwd_forcechange = form.getInputValue('passwd_forcechange',['no'])[0]=='yes'
    passwd_inform = form.getInputValue('passwd_inform',[''])[0]

    password_attr_types_msg = ''

    passwd_modlist = w2lapp.cnf.GetParam(ls,'passwd_modlist',[])

    # Extend with appropriate user-must-change-password-after-reset attribute
    if passwd_forcechange:
      # draft-behera-password-policy
      if sub_schema.sed[ldap0.schema.models.AttributeType].has_key('1.3.6.1.4.1.42.2.27.8.1.22'):
        passwd_modlist.append((ldap0.MOD_REPLACE,'pwdReset','TRUE'))
      # MS AD
      elif sub_schema.sed[ldap0.schema.models.AttributeType].has_key('1.2.840.113556.1.4.96'):
        passwd_modlist.append((ldap0.MOD_REPLACE,'pwdLastSet','0'))

    if not passwd_action:

      raise w2lapp.core.ErrorExit(u'No password action chosen.')

    elif passwd_action=='passwdextop':

      #-------------------------------------------------------
      # Modify password via Password Modify Extended Operation
      #-------------------------------------------------------

      try:
        ls.l.passwd_s(
          passwd_who.encode(ls.charset),
          (old_password or u'').encode(ls.charset) or None,
          passwd_input.encode(ls.charset)
        )
      except (
        ldap0.CONSTRAINT_VIOLATION,
        ldap0.UNWILLING_TO_PERFORM,
      ) as e:
        PasswdForm(
          sid,outf,form,ls,dn,sub_schema,
          passwd_action,passwd_who,user_objectclasses,
          Heading='Password Error',
          Msg=w2lapp.gui.LDAPError2ErrMsg(e,form,ls.charset)
        )
        return
      else:
        if passwd_modlist:
          ls.modifyEntry(passwd_who,passwd_modlist)
        if no_passwd_input:
          password_attr_types_msg = 'Generated password set by the server: %s' % (form.utf2display(passwd_input))
        else:
          password_attr_types_msg = 'Password set by the server.'

    elif passwd_action in ('setuserpassword','setunicodepwd'):

      #-------------------------------------------------------
      # Modify password via Modify Request
      #-------------------------------------------------------

      all_attrs_dict = GetAllAllowedAttributes(sub_schema,user_objectclasses)

      if not all_attrs_dict.has_key('2.5.4.35'):
        # Add a simple AUXILIARY object class for the userPassword attribute if
        # current object classes of entry do not allow userPassword
        for userpassword_class in ('simpleSecurityObject','simpleAuthObject'):
          try:
            if user_objectclasses and \
               not userpassword_class.lower() in user_objectclasses and \
               sub_schema.get_inheritedattr(ldap0.schema.models.ObjectClass,userpassword_class,'kind')==2:
              passwd_modlist.append((ldap0.MOD_ADD,'objectClass',userpassword_class))
              break
          except KeyError:
            pass

      passwd_scheme = form.getInputValue('passwd_scheme',[''])[0]

      # Set "standard" password of LDAP entry
      if all_attrs_dict.has_key('1.2.840.113556.1.4.90'):
        # Active Directory's password attribute unicodePwd
        passwd_attr_type = 'unicodePwd'
        unicodePwd = ldaputil.passwd.UnicodePwd(
          l=ls.l,
          dn=passwd_who.encode(ls.charset)
        )
        new_passwd_value = unicodePwd.encodePassword(passwd_input)
        passwd_scheme = ''
        if old_password:
          old_passwd_value = unicodePwd.encodePassword(old_password)
      else:
        # Assume standard password attribute userPassword
        passwd_attr_type = 'userPassword'
        userPassword = ldaputil.passwd.UserPassword(
          l=ls.l,
          dn=passwd_who.encode(ls.charset),
          charset=ls.charset,
        )
        # Work around the problem that LDAP applications use different
        # charset encodings for the userPassword attribute
        new_passwd_value = userPassword.encodePassword(passwd_input,passwd_scheme)
        if old_password:
          old_passwd_value = userPassword.encodePassword(old_password,'')

      if OwnPwdChange(ls,passwd_who) and old_password:
        passwd_modlist.extend((
          (ldap0.MOD_DELETE,passwd_attr_type,[old_passwd_value]),
          (ldap0.MOD_ADD,passwd_attr_type,[new_passwd_value]),
        ))
      else:
        passwd_modlist.append(
          (ldap0.MOD_REPLACE,passwd_attr_type,[new_passwd_value]),
        )

      passwd_settimesync = form.getInputValue('passwd_settimesync',['no'])[0]=='yes'

      pwd_change_timestamp = time.time()

      if passwd_settimesync and all_attrs_dict.has_key('1.3.6.1.1.1.1.5'):
        passwd_modlist.append((ldap0.MOD_REPLACE,'shadowLastChange',str(int(pwd_change_timestamp/86400))))

      passwd_ntpasswordsync = form.getInputValue('passwd_ntpasswordsync',['no'])[0]=='yes'

      # Samba password synchronization if requested
      if passwd_ntpasswordsync and all_attrs_dict.has_key('1.3.6.1.4.1.7165.2.1.25'):
        passwd_modlist.append((ldap0.MOD_REPLACE,'sambaNTPassword',NtPasswordHash(passwd_input)))
        if passwd_settimesync and all_attrs_dict.has_key('1.3.6.1.4.1.7165.2.1.27'):
          passwd_modlist.append((ldap0.MOD_REPLACE,'sambaPwdLastSet',str(int(pwd_change_timestamp))))

      password_attr_types_msg = 'Password-related attributes set: %s' % (', '.join(
        [
          form.utf2display(unicode(attr_type))
          for _, attr_type, _ in passwd_modlist
        ]
      ))
      if no_passwd_input:
        password_attr_types_msg += '<br>Generated password is: %s' % (form.utf2display(passwd_input))

      # Modify password
      try:
        ls.modifyEntry(passwd_who,passwd_modlist)
      except (
        ldap0.CONSTRAINT_VIOLATION,
        ldap0.UNWILLING_TO_PERFORM,
      ) as e:
        PasswdForm(
          sid,outf,form,ls,dn,sub_schema,
          passwd_action,passwd_who,user_objectclasses,
          Heading='Password Error',
          Msg=w2lapp.gui.LDAPError2ErrMsg(e,form,ls.charset)
        )
        return
      except ldap0.NO_SUCH_ATTRIBUTE as e:
        PasswdForm(
          sid,outf,form,ls,dn,sub_schema,
          passwd_action,passwd_who,user_objectclasses,
          Heading='Password Error',
          Msg=w2lapp.gui.LDAPError2ErrMsg(
            e,form,ls.charset,template=r"%s (Hint: Try without old password.)"
          )
        )
        return


    # Check if relogin is necessary
    if OwnPwdChange(ls,passwd_who):
      # Force reconnecting without bind
      # FIX ME! not really thread-safe
      ls.l._last_bind = None
      try:
        ls.l.reconnect(ls.uri)
      except ldap0.INAPPROPRIATE_AUTH:
        pass
      ls.who = None
      # Display login form
      w2lapp.login.w2l_Login(
        sid,outf,'searchform',form,ls,dn,connLDAPUrl,None,ls.getSearchRoot(passwd_who),
        login_msg='New login is required!<br>'+password_attr_types_msg,
        who=passwd_who,relogin=0,nomenu=1
      )
    else:
      if passwd_inform=='display_url':
        passwd_link = '<a href="%s">Password change URL</a>' % (PasswordChangeUrl(form,ls,passwd_who,passwd_input))
      else:
        passwd_link = ''
      w2lapp.gui.SimpleMessage(
        sid,outf,command,form,ls,dn,
        message="""
        <p class="SuccessMessage">Changed password of entry %s</p>
        <p>%s</p>
        <p>%s</p>
        """ % (
          w2lapp.gui.DisplayDN(sid,form,ls,passwd_who),
          password_attr_types_msg,
          passwd_link,
        ),
        main_menu_list=w2lapp.gui.MainMenu(sid,form,ls,dn),
        context_menu_list=w2lapp.gui.ContextMenuSingleEntry(sid,form,ls,dn)
      )

  else:

    ####################################################################
    # New password not yet provided => ask for it
    ####################################################################

    PasswdForm(
      sid,outf,form,ls,dn,sub_schema,
      passwd_action,passwd_who,
      user_objectclasses,'Set password',''
    )
