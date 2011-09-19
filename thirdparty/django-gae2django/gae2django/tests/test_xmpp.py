# Tests for a stub XMPP module.

import unittest

from gae2django.gaeapi.appengine.api import xmpp


class TestModuleFunctions(unittest.TestCase):

    def test_get_presence(self):
        self.assertEqual(xmpp.get_presence('foo@gmail.com'), False)
        self.assertEqual(xmpp.get_presence('foo@gmail.com', 'from@gmail.com'),
                         False)

    def test_send_invite(self):
        self.assertEqual(xmpp.send_invite('foo@gmail.com'), None)
        self.assertEqual(xmpp.send_invite('foo@gmail.com', 'from'), None)

    def test_send_message(self):
        self.assertEqual(xmpp.send_message('foo', 'body'),
                         xmpp.NO_ERROR)
        self.assertEqual(xmpp.send_message(['foo'], 'body'),
                         [xmpp.NO_ERROR])
        self.assertEqual(xmpp.send_message(['foo', 'bar'], 'body'),
                         [xmpp.NO_ERROR, xmpp.NO_ERROR])
        # Should ignore additional positional arguments and keywords
        self.assertEqual(xmpp.send_message('foo', 'body', 'from', 'msg_type',
                                           raw_xml=True),
                         xmpp.NO_ERROR)


class TestModuleNamespace(unittest.TestCase):

    def test_errors(self):
        self.assertEqual(xmpp.NO_ERROR, 0)
        self.assertEqual(xmpp.INVALID_JID, 1)
        self.assertEqual(xmpp.OTHER_ERROR, 2)

    def test_message_types(self):
        self.assertEqual(xmpp.MESSAGE_TYPE_CHAT, 'chat')
        self.assertEqual(xmpp.MESSAGE_TYPE_ERROR, 'error')
        self.assertEqual(xmpp.MESSAGE_TYPE_GROUPCHAT, 'groupchat')
        self.assertEqual(xmpp.MESSAGE_TYPE_HEADLINE, 'headline')
        self.assertEqual(xmpp.MESSAGE_TYPE_NORMAL, 'normal')

    def test_message(self):
        self.assert_(hasattr(xmpp, 'Message'))

    def test_invalid_message_error(self):
        self.assert_(hasattr(xmpp, 'InvalidMessageError'))


class TestMessage(unittest.TestCase):

    def test_constructor(self):
        data = {}
        self.assertRaises(xmpp.InvalidMessageError,
                          xmpp.Message, data)
        data['from'] = 'from'
        self.assertRaises(xmpp.InvalidMessageError,
                          xmpp.Message, data)
        data['to'] = 'to'
        self.assertRaises(xmpp.InvalidMessageError,
                          xmpp.Message, data)
        data['body'] = 'body'
        self.assert_(isinstance(xmpp.Message(data), xmpp.Message))

    def test_message_properties(self):
        msg = xmpp.Message({'from': 'from', 'to': 'to', 'body': 'body'})
        self.assertEqual(msg.sender, 'from')
        self.assertEqual(msg.to, 'to')
        self.assertEqual(msg.body, 'body')
        self.assertEqual(msg.command, None)
        self.assertEqual(msg.arg, 'body')

    def test_reply(self):
        msg = xmpp.Message({'from': 'from', 'to': 'to', 'body': 'body'})
        self.assertEqual(msg.reply('reply'), xmpp.NO_ERROR)
        self.assertEqual(msg.reply('reply', raw_xml=True), xmpp.NO_ERROR)
