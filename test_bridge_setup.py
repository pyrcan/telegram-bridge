"""Synthetic sealed setup only: no Telegram, real keys or live app writes."""
import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import bridge_setup as setup
import connect_telegram as sealed

KEY = '123:' + 'a' * 24

class SetupTests(unittest.TestCase):
    def test_verify_then_encrypt_and_start(self):
        inspect = Mock(side_effect=[{'is_bot': True}, {'url': ''}])
        api = Mock()
        setup.connect({'fields': {'bot_token': KEY}}, api, 18, inspect)
        self.assertEqual([call.args[1] for call in inspect.call_args_list], ['getMe', 'getWebhookInfo'])
        self.assertEqual(api.call_args_list[0].args, ('/api/apps/18/secrets/bot-token', {'value': KEY}))
        self.assertEqual(api.call_args_list[0].kwargs, {'method': 'PUT'})
        self.assertEqual(api.call_args_list[1].args[0], '/api/apps/18/run-job')

    def test_invalid_key_or_webhook_never_writes(self):
        for key, bot, hook in [('bad', {}, {}), (KEY, {'is_bot':False}, {}), (KEY, {'is_bot':True}, {'url':'https://example.test'})]:
            api = Mock()
            with self.assertRaises(ValueError):
                setup.connect({'fields': {'bot_token': key}}, api, 18, Mock(side_effect=[bot, hook]))
            api.assert_not_called()

    def test_app_token_cannot_execute_setup(self):
        with patch.dict(os.environ, {'AGENT_TOKEN':'synthetic-owner', 'APP_TOKEN':'fixture'}):
            with self.assertRaises(ValueError):
                sealed.api('/api/apps/18/secrets/bot-token')

    def test_redirects_refused_and_ui_never_collects_keys(self):
        self.assertIsNone(__import__('telegram_http').NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.test'))
        source = Path(__file__).with_name('index.jsx').read_text()
        for forbidden in ('setBotToken', 'type="password"', 'JSON.stringify({ value })'):
            self.assertNotIn(forbidden, source)
        self.assertIn("'Telegram Bridge','connect-telegram'", source)

if __name__ == '__main__': unittest.main()
