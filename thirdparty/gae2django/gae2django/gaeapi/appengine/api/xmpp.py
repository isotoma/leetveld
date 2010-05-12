"""Stub XMPP module that does nothing except exposing the API."""

NO_ERROR = 0
INVALID_JID = 1
OTHER_ERROR = 2

MESSAGE_TYPE_CHAT = 'chat'
MESSAGE_TYPE_ERROR = 'error'
MESSAGE_TYPE_GROUPCHAT = 'groupchat'
MESSAGE_TYPE_HEADLINE = 'headline'
MESSAGE_TYPE_NORMAL = 'normal'


class Error(Exception):
    pass

class InvalidJidError(Error):
    pass

class InvalidTypeError(Error):
    pass

class InvalidXmlError(Error):
    pass

class NoBodyError(Error):
    pass

class InvalidMessageError(Error):
    pass


class Message(object):

    def __init__(self, args):
        try:
            self.sender = args['from']
            self.to = args['to']
            self.body = args['body']
        except KeyError, err:
            raise InvalidMessageError(err)
        self.command = None
        self.arg = 'body'

    def reply(self, body, message_type=MESSAGE_TYPE_CHAT, raw_xml=False):
        return NO_ERROR


def get_presence(jid, from_jid=None):
    return False


def send_invite(jid, from_jid=None):
    return None


def send_message(jids, body, *args, **kwds):
    if isinstance(jids, basestring):
        return NO_ERROR
    return [NO_ERROR]*len(jids)
