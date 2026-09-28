"""Coalesced Telegram reply drafts; provider stream consumption never waits on I/O."""
import threading
import time


class ReplyProgress:
  def __init__(self, send_text, send_thinking, *, interval=1.0):
    self.send_text = send_text
    self.send_thinking = send_thinking
    self.interval = interval
    self.changed = threading.Event()
    self.stop = threading.Event()
    self.lock = threading.Lock()
    self.text = ''
    self.sent = None
    self.sent_at = 0.0
    self.started = time.monotonic()
    self.worker = threading.Thread(target=self._run, name='telegram-reply-draft', daemon=True)

  def show(self, text):
    with self.lock:
      self.text = str(text or '')[-3900:]
    self.changed.set()

  def _run(self):
    next_send = 0.0
    while not self.stop.is_set():
      wait = max(0, next_send - time.monotonic())
      if self.stop.wait(wait):
        return
      with self.lock:
        text = self.text
      if text:
        if text != self.sent or time.monotonic() - self.sent_at >= 20:
          self.send_text(text)
          self.sent = text
          self.sent_at = time.monotonic()
      else:
        self.send_thinking(max(0, int(time.monotonic() - self.started)))
      next_send = time.monotonic() + self.interval
      self.changed.clear()
      # Wake promptly for the first text, but never exceed the configured rate.
      self.changed.wait(self.interval)

  def __enter__(self):
    self.worker.start()
    return self

  def __exit__(self, *args):
    self.stop.set()
    self.changed.set()
    # Keep the existing bounded shutdown: never wait a full Telegram timeout
    # just to retire a cosmetic draft. Completed final delivery stays canonical.
    self.worker.join(timeout=1)
