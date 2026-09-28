"""Sealed owner setup. Keys never pass through the app frame or its state."""
import re


def inspect_bot(token, method):
    from telegram_http import call
    if method not in ('getMe', 'getWebhookInfo'):
        raise ValueError('Unsupported setup check')
    return call(token, method)


def connect(request, api, app_id, inspect=inspect_bot):
    token = request.get('fields', {}).get('bot_token', '').strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,150}', token):
        raise ValueError('Invalid bot key')
    bot = inspect(token, 'getMe')
    hook = inspect(token, 'getWebhookInfo')
    if not bot.get('is_bot') or hook.get('url'):
        raise ValueError('Use a dedicated bot without a webhook')
    api(f'/api/apps/{app_id}/secrets/bot-token', {'value': token}, method='PUT')
    # Polling remains controlled by settings.enabled and accepts only the paired
    # owner account. The trusted form explains this effect before submission.
    api(f'/api/apps/{app_id}/run-job', {}, method='POST')
