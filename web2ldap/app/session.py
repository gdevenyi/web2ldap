# -*- coding: utf-8 -*-
"""
web2ldap.app.session: The session handling thingy

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2018 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import absolute_import

import time,traceback,collections

import pyweblib.session

from web2ldap.ldapsession import LDAPSession
import web2ldapcnf
from web2ldap.log import logger

class InvalidSessionInstance(pyweblib.session.SessionException):
  pass


class WrongSessionCookie(pyweblib.session.SessionException):
  pass


class Session(pyweblib.session.WebSession):

  def __init__(
    self,
    dictobj=None,
    expireDeactivate=0,
    expireRemove=0,
    crossCheckVars=None,
    maxSessionCount=None,
    sessionIDLength=12,
    sessionIDChars=None,
    maxSessionCountPerIP=None,
  ):
    pyweblib.session.WebSession.__init__(
      self,
      dictobj,
      expireDeactivate,
      expireRemove,
      crossCheckVars,
      maxSessionCount,
      sessionIDLength,
      sessionIDChars,
    )
    self.max_concurrent_sessions = 0
    self.remote_ip_sessions = collections.defaultdict(set)
    self.session_ip_addr = {}
    self.maxSessionCountPerIP = maxSessionCountPerIP or self.maxSessionCount/4
    self.remote_ip_counter = collections.Counter()
    logger.debug('Initialized clean-up thread %s[%x]', self.__class__.__name__, id(self))

  def _remote_ip(self,env):
    return env.get('FORWARDED_FOR',
           env.get('HTTP_X_FORWARDED_FOR',
           env.get('HTTP_X_REAL_IP',
           env.get('REMOTE_HOST',
           env.get('REMOTE_ADDR','__UNKNOWN__')))))

  def newSession(self,env=None):
    remote_ip = self._remote_ip(env)
    remote_ip_sessions = self.remote_ip_sessions.get(remote_ip,set())
    if len(remote_ip_sessions)>=self.maxSessionCountPerIP:
      raise pyweblib.session.MaxSessionCountExceeded(self.maxSessionCountPerIP)
    session_id = pyweblib.session.WebSession.newSession(self,env)
    current_concurrent_sessions = len(self.sessiondict)/2
    if current_concurrent_sessions>self.max_concurrent_sessions:
      self.max_concurrent_sessions = current_concurrent_sessions
    self.session_ip_addr[session_id] = remote_ip
    self.remote_ip_counter.update({remote_ip:1})
    self.remote_ip_sessions[remote_ip].add(session_id)
    return session_id

  def _remove_ip_assoc(self,sid,remote_ip):
    try:
      del self.session_ip_addr[sid]
    except KeyError:
      pass
    try:
      self.remote_ip_sessions[remote_ip].remove(sid)
    except KeyError:
      pass
    else:
      if not self.remote_ip_sessions[remote_ip]:
        del self.remote_ip_sessions[remote_ip]
    return # _remove_ip_assoc()

  def renameSession(self,old_sid,env):
    session_data = self.retrieveSession(old_sid,env)
    new_sid = self.newSession(env)
    self.storeSession(new_sid,session_data)
    pyweblib.session.WebSession.deleteSession(self,old_sid)
    # Set new remote IP associations
    remote_ip = self._remote_ip(env)
    self.session_ip_addr[new_sid] = remote_ip
    # Remove old remote IP associations
    self._remove_ip_assoc(old_sid,remote_ip)
    return new_sid

  def deleteSession(self,sid):
    try:
      ls_local = self.sessiondict[sid][1]
    except KeyError:
      pass
    else:
      if isinstance(ls_local,LDAPSession):
        ls_local.unbind()
    pyweblib.session.WebSession.deleteSession(self,sid)
    # Remove old remote IP associations
    try:
      remote_ip = self.session_ip_addr[sid]
    except KeyError:
      pass
    else:
      self._remove_ip_assoc(sid,remote_ip)
    return # deleteSession()


class CleanUpThread(pyweblib.session.CleanUpThread):
  """
  Thread class for clean-up thread

  Mainly it overrides pyweblib.session.CleanUpThread.run()
  to call ldapSession.unbind().
  """

  def __init__(self,*args,**kwargs):
    pyweblib.session.CleanUpThread.__init__(self,*args,**kwargs)
    self.removed_sessions = 0
    self.run_counter = 0
    self.last_run_time = 0
    self.enabled = True

  def run(self):
    """Thread function for cleaning up session database"""
    logger.debug('Entering %s[%x].run()', self.__class__.__name__, id(self))
    while self.enabled and not self._stop_event.isSet():
      logger.debug('%s[%x].run()', self.__class__.__name__, id(self))
      self.run_counter += 1
      current_time = time.time()
      try:
        sessiondict_keys = [
          sid
          for sid in globals()['session_store'].sessiondict.keys()
          if not sid.startswith('__')
        ]
        for session_id in sessiondict_keys:
          try:
            session_timestamp,_ = self._sessionInstance.sessiondict[session_id]
          except KeyError:
            # Avoid race condition. The session might have been
            # deleted in the meantime. But make sure everything is deleted.
            self._sessionInstance.deleteSession(session_id)
          else:
            # Check expiration time
            if session_timestamp+self._sessionInstance.expireRemove<current_time:
              # Remove expired session
              self._sessionInstance.deleteSession(session_id)
              self.removed_sessions+=1
        self.last_run_time = current_time
      except KeyboardInterrupt:
        logger.debug('Caught KeyboardInterrupt exception in %s[%x].run()', self.__class__.__name__, id(self))
        break
      except Exception as err:
        # Catch all exceptions to avoid thread being killed.
        logger.error('Unhandled exception in %s[%x].run()', self.__class__.__name__, id(self), exc_info=True)

      # Sleeping until next turn
      self._stop_event.wait(self._interval)

    logger.debug('Exiting %s[%x].run()', self.__class__.__name__, id(self))
    return # CleanUpThread.run()


########################################################################
# Initialize web session object
########################################################################

global session_store
session_store = Session(
  expireDeactivate=web2ldapcnf.session_remove,
  expireRemove=web2ldapcnf.session_remove,
  crossCheckVars = web2ldapcnf.session_checkvars,
  maxSessionCount = web2ldapcnf.session_limit,
  maxSessionCountPerIP = web2ldapcnf.session_per_ip_limit,
)
logger.debug('Initialized web2ldap session store %r', session_store)

global cleanUpThread
cleanUpThread = CleanUpThread(session_store,interval=5)
cleanUpThread.start()
logger.debug('Started clean-up thread %s[%x]', cleanUpThread.__class__.__name__, id(cleanUpThread))
