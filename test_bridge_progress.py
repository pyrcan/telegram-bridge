import threading
import time
import unittest

from bridge_progress import ReplyProgress


class ProgressTests(unittest.TestCase):
  def test_stream_updates_never_wait_on_network_and_coalesce(self):
    entered = threading.Event()
    release = threading.Event()
    shown = threading.Event()
    texts = []
    def thinking(elapsed):
      entered.set()
      release.wait(1)
    def text(value):
      texts.append(value)
      shown.set()
    with ReplyProgress(text, thinking, interval=0.01) as progress:
      self.assertTrue(entered.wait(0.5))
      started = time.monotonic()
      for i in range(100):
        progress.show('answer ' + str(i))
      self.assertLess(time.monotonic() - started, 0.1)
      release.set()
      self.assertTrue(shown.wait(0.5))
    self.assertEqual(texts, ['answer 99'])
    self.assertFalse(progress.worker.is_alive())

  def test_stopped_progress_never_sends_queued_text(self):
    texts = []
    with ReplyProgress(texts.append, lambda _: None, interval=0.1) as progress:
      progress.show('queued')
    count = len(texts)
    time.sleep(0.12)
    self.assertEqual(len(texts), count)
