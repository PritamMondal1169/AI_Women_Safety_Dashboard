"""
utils/twilio_alerts.py — Twilio SMS, Voice Call, and WhatsApp alert dispatcher.

Channels:
  SMS     — Text message sent to all configured numbers.
  Voice   — Automated phone call with TTS spoken alert message.
  WhatsApp— WhatsApp message via Twilio sandbox / verified number.

Fallback:
  If Twilio fails, Africa's Talking is tried for SMS (if configured).

Setup:
  1. Sign up at https://www.twilio.com/try-twilio (free $15 trial credit)
  2. Get your Account SID, Auth Token from the Twilio Console
  3. Buy or use trial phone number
  4. Set values in .env (see bottom of this file)

Install:
  pip install twilio

Test without running the full pipeline:
  python utils/twilio_alerts.py --test-sms
  python utils/twilio_alerts.py --test-call
  python utils/twilio_alerts.py --test-whatsapp
  python utils/twilio_alerts.py --check
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import alert_cfg
from utils.logger import get_logger

log = get_logger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_DELAY    = 4.0   # seconds between retries


# ---------------------------------------------------------------------------
# TwilioAlerter
# ---------------------------------------------------------------------------
class TwilioAlerter:
    """
    Sends SMS, Voice calls, and WhatsApp messages via Twilio API.
    All sends run in daemon threads — never blocks the CV loop.
    """

    def __init__(self) -> None:
        self._client = None
        self._ready  = False
        self._lock   = threading.Lock()
        self._init_client()

    def _init_client(self) -> None:
        if not alert_cfg.TWILIO_ENABLED:
            log.info("Twilio disabled (TWILIO_ENABLED=false in .env)")
            return

        if not alert_cfg.TWILIO_ACCOUNT_SID or \
           alert_cfg.TWILIO_ACCOUNT_SID.startswith("ACxxx"):
            log.warning("Twilio SID not configured. Set TWILIO_ACCOUNT_SID in .env")
            return

        if not alert_cfg.TWILIO_AUTH_TOKEN or \
           alert_cfg.TWILIO_AUTH_TOKEN == "your_auth_token_here":
            log.warning("Twilio Auth Token not configured. Set TWILIO_AUTH_TOKEN in .env")
            return

        if not alert_cfg.TWILIO_FROM_NUMBER:
            log.warning("TWILIO_FROM_NUMBER not set in .env")
            return

        if not alert_cfg.to_numbers:
            log.warning("TWILIO_TO_NUMBERS not set in .env")
            return

        try:
            from twilio.rest import Client
            self._client = Client(
                alert_cfg.TWILIO_ACCOUNT_SID,
                alert_cfg.TWILIO_AUTH_TOKEN,
            )
            self._ready = True
            log.info(
                "Twilio ready | from={f} | to={t} | sms={s} | voice={v} | wa={w}",
                f=alert_cfg.TWILIO_FROM_NUMBER,
                t=alert_cfg.to_numbers,
                s=alert_cfg.TWILIO_SMS_ENABLED,
                v=alert_cfg.TWILIO_VOICE_ENABLED,
                w=alert_cfg.TWILIO_WHATSAPP_ENABLED,
            )
        except ImportError:
            log.error(
                "twilio package not installed. Run: pip install twilio"
            )
        except Exception:
            log.exception("Twilio client init failed.")

    @property
    def ready(self) -> bool:
        return self._ready and self._client is not None

    # ── Public dispatch ───────────────────────────────────────────────────────

    def dispatch(
        self,
        threat_level: str,
        threat_score: float,
        location:     str,
        track_id:     int,
        snapshot_path: Optional[str] = None,
    ) -> dict:
        """
        Fire all configured Twilio channels based on threat level.

        Returns a dict of {channel: True/False} indicating what fired.
        All sends are asynchronous (daemon threads).
        """
        if not self.ready:
            return {}

        fired = {}

        # SMS
        if alert_cfg.TWILIO_SMS_ENABLED and \
           threat_level in alert_cfg.sms_levels:
            threading.Thread(
                target=self._send_sms_all,
                args=(threat_level, threat_score, location, track_id, snapshot_path),
                daemon=True,
            ).start()
            fired["sms"] = True

        # Voice call
        if alert_cfg.TWILIO_VOICE_ENABLED and \
           threat_level in alert_cfg.call_levels:
            threading.Thread(
                target=self._make_call_all,
                args=(threat_level, threat_score, location, track_id),
                daemon=True,
            ).start()
            fired["call"] = True

        # WhatsApp
        if alert_cfg.TWILIO_WHATSAPP_ENABLED and \
           threat_level in alert_cfg.whatsapp_levels:
            threading.Thread(
                target=self._send_whatsapp_all,
                args=(threat_level, threat_score, location, track_id, snapshot_path),
                daemon=True,
            ).start()
            fired["whatsapp"] = True

        return fired

    # ── SMS ───────────────────────────────────────────────────────────────────

    def _send_sms_all(
        self,
        threat_level:  str,
        threat_score:  float,
        location:      str,
        track_id:      int,
        snapshot_path: Optional[str],
    ) -> None:
        """Send SMS to all configured numbers."""
        body = self._sms_body(threat_level, threat_score, location, track_id)

        # Check if we can send MMS (image) — only on US/Canada numbers
        media_url = None
        if snapshot_path:
            snap = Path(snapshot_path)
            if snap.exists():
                # NOTE: For MMS, the image must be publicly accessible via URL.
                # In a production deployment you would upload to S3/Cloudinary first.
                # For now we send SMS only (text) and note snapshot was saved locally.
                log.debug(
                    "Snapshot saved locally at {p} (MMS requires public URL)", p=snap
                )

        for number in alert_cfg.to_numbers:
            self._send_sms_one(number, body, media_url)

    def _send_sms_one(
        self,
        to:        str,
        body:      str,
        media_url: Optional[str] = None,
    ) -> bool:
        """Send SMS to one number with retry."""
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                kwargs = {
                    "body": body,
                    "from_": alert_cfg.TWILIO_FROM_NUMBER,
                    "to":    to,
                }
                if media_url:
                    kwargs["media_url"] = [media_url]

                msg = self._client.messages.create(**kwargs)
                log.success(
                    "SMS sent | to={t} | sid={s}", t=to, s=msg.sid
                )
                return True

            except Exception as exc:
                log.warning(
                    "SMS failed (attempt {a}/{m}) to {t}: {e}",
                    a=attempt, m=_RETRY_ATTEMPTS, t=to, e=exc,
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_DELAY)

        log.error("SMS failed after {m} attempts to {t}", m=_RETRY_ATTEMPTS, t=to)
        return False

    @staticmethod
    def _sms_body(
        threat_level: str,
        threat_score: float,
        location:     str,
        track_id:     int,
    ) -> str:
        emoji = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}.get(threat_level, "⚠️")
        import datetime
        now = datetime.datetime.now().strftime("%H:%M:%S")
        return (
            f"{emoji} WOMEN SAFETY ALERT\n"
            f"Level: {threat_level} ({threat_score:.0%})\n"
            f"Track: #{track_id}\n"
            f"Location: {location}\n"
            f"Time: {now}\n"
            f"Check dashboard immediately."
        )

    # ── Voice call ────────────────────────────────────────────────────────────

    def _make_call_all(
        self,
        threat_level: str,
        threat_score: float,
        location:     str,
        track_id:     int,
    ) -> None:
        """Place automated voice call to all configured numbers."""
        twiml = self._call_twiml(threat_level, threat_score, location)
        for number in alert_cfg.to_numbers:
            self._make_call_one(number, twiml)

    def _make_call_one(self, to: str, twiml: str) -> bool:
        """Place one automated voice call with retry."""
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                call = self._client.calls.create(
                    twiml=twiml,
                    from_=alert_cfg.TWILIO_FROM_NUMBER,
                    to=to,
                    timeout=30,      # ring for 30 seconds
                    machine_detection="Enable",  # detect voicemail
                )
                log.success(
                    "Call placed | to={t} | sid={s}", t=to, s=call.sid
                )
                return True

            except Exception as exc:
                log.warning(
                    "Call failed (attempt {a}/{m}) to {t}: {e}",
                    a=attempt, m=_RETRY_ATTEMPTS, t=to, e=exc,
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_DELAY)

        log.error("Call failed after {m} attempts to {t}", m=_RETRY_ATTEMPTS, t=to)
        return False

    @staticmethod
    def _call_twiml(
        threat_level: str,
        threat_score: float,
        location:     str,
    ) -> str:
        """
        Generate TwiML for automated voice call.
        Twilio reads this XML and converts it to speech using TTS.
        """
        lang = alert_cfg.TWILIO_VOICE_LANGUAGE
        pct  = int(threat_score * 100)

        # Voice selection based on language
        voice_map = {
            "en-IN": "Polly.Aditi",      # Indian English female
            "en-US": "Polly.Joanna",     # American English female
            "en-GB": "Polly.Amy",        # British English female
            "hi-IN": "Polly.Aditi",      # Hindi (Aditi supports Hindi too)
        }
        voice = voice_map.get(lang, "Polly.Joanna")

        message = (
            f"Alert. Alert. This is an automated Women Safety Alert. "
            f"A {threat_level} level threat has been detected. "
            f"Threat score is {pct} percent. "
            f"Location: {location}. "
            f"Please check the monitoring dashboard immediately. "
            f"I repeat, this is a {threat_level} threat. "
            f"Please respond immediately."
        )

        # Pause between repetitions, repeat message twice
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="{voice}" language="{lang}">{message}</Say>
  <Pause length="2"/>
  <Say voice="{voice}" language="{lang}">{message}</Say>
  <Pause length="1"/>
  <Say voice="{voice}" language="{lang}">
    This alert has been logged. Goodbye.
  </Say>
</Response>"""

    # ── WhatsApp ──────────────────────────────────────────────────────────────

    def _send_whatsapp_all(
        self,
        threat_level:  str,
        threat_score:  float,
        location:      str,
        track_id:      int,
        snapshot_path: Optional[str],
    ) -> None:
        """Send WhatsApp message to all configured numbers."""
        body = self._whatsapp_body(threat_level, threat_score, location, track_id)
        for number in alert_cfg.to_numbers:
            wa_to = f"whatsapp:{number}"
            self._send_whatsapp_one(wa_to, body)

    def _send_whatsapp_one(self, to: str, body: str) -> bool:
        """Send WhatsApp message to one number with retry."""
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                msg = self._client.messages.create(
                    body=body,
                    from_=alert_cfg.TWILIO_WHATSAPP_FROM,
                    to=to,
                )
                log.success(
                    "WhatsApp sent | to={t} | sid={s}", t=to, s=msg.sid
                )
                return True

            except Exception as exc:
                log.warning(
                    "WhatsApp failed (attempt {a}/{m}) to {t}: {e}",
                    a=attempt, m=_RETRY_ATTEMPTS, t=to, e=exc,
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_DELAY)

        log.error("WhatsApp failed after {m} attempts to {t}", m=_RETRY_ATTEMPTS, t=to)
        return False

    @staticmethod
    def _whatsapp_body(
        threat_level: str,
        threat_score: float,
        location:     str,
        track_id:     int,
    ) -> str:
        emoji = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}.get(threat_level, "⚠️")
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{emoji} *WOMEN SAFETY ALERT*\n\n"
            f"*Level:* {threat_level}\n"
            f"*Score:* {threat_score:.1%}\n"
            f"*Track ID:* #{track_id}\n"
            f"*Location:* {location}\n"
            f"*Time:* {now}\n\n"
            f"⚠️ Please check the monitoring dashboard immediately.\n"
            f"_Automated alert — Women Safety Edge-AI System_"
        )

    # ── Test methods ──────────────────────────────────────────────────────────

    def test_sms(self) -> bool:
        log.info("Sending test SMS to {n}…", n=alert_cfg.to_numbers)
        body = self._sms_body("HIGH", 0.95, "Test Location", 0)
        results = [self._send_sms_one(n, body) for n in alert_cfg.to_numbers]
        return any(results)

    def test_call(self) -> bool:
        log.info("Placing test call to {n}…", n=alert_cfg.to_numbers)
        twiml = self._call_twiml("HIGH", 0.95, "Test Location")
        results = [self._make_call_one(n, twiml) for n in alert_cfg.to_numbers]
        return any(results)

    def test_whatsapp(self) -> bool:
        log.info("Sending test WhatsApp to {n}…", n=alert_cfg.to_numbers)
        body = self._whatsapp_body("HIGH", 0.95, "Test Location", 0)
        results = [
            self._send_whatsapp_one(f"whatsapp:{n}", body)
            for n in alert_cfg.to_numbers
        ]
        return any(results)


# ---------------------------------------------------------------------------
# Africa's Talking — free SMS fallback
# ---------------------------------------------------------------------------
class AfricasTalkingAlerter:
    """
    Free SMS via Africa's Talking.
    Free sandbox for testing; pay-as-you-go for production.
    Sign up: https://africastalking.com
    """

    def __init__(self) -> None:
        self._sms    = None
        self._ready  = False
        self._init()

    def _init(self) -> None:
        if not alert_cfg.AFRICASTALKING_ENABLED:
            return
        if not alert_cfg.AFRICASTALKING_API_KEY or \
           alert_cfg.AFRICASTALKING_API_KEY == "your_api_key_here":
            log.warning("Africa's Talking API key not configured.")
            return
        try:
            import africastalking
            africastalking.initialize(
                alert_cfg.AFRICASTALKING_USERNAME,
                alert_cfg.AFRICASTALKING_API_KEY,
            )
            self._sms   = africastalking.SMS
            self._ready = True
            log.info(
                "Africa's Talking ready | username={u}",
                u=alert_cfg.AFRICASTALKING_USERNAME,
            )
        except ImportError:
            log.error(
                "africastalking package not installed. "
                "Run: pip install africastalking"
            )
        except Exception:
            log.exception("Africa's Talking init failed.")

    @property
    def ready(self) -> bool:
        return self._ready and self._sms is not None

    def send_sms(
        self,
        threat_level: str,
        threat_score: float,
        location:     str,
        track_id:     int,
    ) -> bool:
        if not self.ready:
            return False

        message = (
            f"WOMEN SAFETY ALERT [{threat_level}] "
            f"Score:{threat_score:.0%} "
            f"Track:#{track_id} "
            f"Location:{location}"
        )

        recipients = alert_cfg.to_numbers
        if not recipients:
            log.warning("No recipient numbers configured.")
            return False

        try:
            kwargs = {
                "message":    message,
                "recipients": recipients,
            }
            if alert_cfg.AFRICASTALKING_FROM:
                kwargs["sender_id"] = alert_cfg.AFRICASTALKING_FROM

            result = self._sms.send(**kwargs)
            log.success(
                "Africa's Talking SMS sent | result={r}", r=result
            )
            return True
        except Exception:
            log.exception("Africa's Talking SMS failed.")
            return False

    def test_sms(self) -> bool:
        return self.send_sms("HIGH", 0.95, "Test Location", 0)


# ---------------------------------------------------------------------------
# Unified MultiChannelAlerter — use this in main.py
# ---------------------------------------------------------------------------
class MultiChannelAlerter:
    """
    Single entry point for all external alert channels.
    Wraps Twilio + Africa's Talking with automatic fallback.

    Usage in main.py:
        from utils.twilio_alerts import MultiChannelAlerter
        alerter = MultiChannelAlerter()

        # On threat detected:
        alerter.dispatch(
            threat_level="HIGH",
            threat_score=0.92,
            location="Kolkata, India",
            track_id=3,
            snapshot_path="data/alert_3_1234.jpg",
        )
    """

    def __init__(self) -> None:
        self.twilio = TwilioAlerter()
        self.at     = AfricasTalkingAlerter()
        self._stats = {"sms": 0, "call": 0, "whatsapp": 0, "at_sms": 0}

    def dispatch(
        self,
        threat_level:  str,
        threat_score:  float,
        location:      str,
        track_id:      int,
        snapshot_path: Optional[str] = None,
    ) -> dict:
        """
        Fire all available channels based on threat level.
        Falls back to Africa's Talking SMS if Twilio SMS fails.
        """
        fired = {}

        # Primary: Twilio
        if self.twilio.ready:
            twilio_fired = self.twilio.dispatch(
                threat_level, threat_score, location, track_id, snapshot_path
            )
            fired.update(twilio_fired)
            for k in twilio_fired:
                self._stats[k] = self._stats.get(k, 0) + 1

        # Fallback: Africa's Talking SMS (if Twilio not available or failed)
        if not fired.get("sms") and self.at.ready:
            if threat_level in alert_cfg.sms_levels:
                threading.Thread(
                    target=self.at.send_sms,
                    args=(threat_level, threat_score, location, track_id),
                    daemon=True,
                ).start()
                fired["at_sms"] = True
                self._stats["at_sms"] += 1
                log.info("Africa's Talking SMS fallback triggered.")

        if not fired:
            log.debug(
                "No external channels fired for {l} — "
                "configure Twilio or Africa's Talking in .env",
                l=threat_level,
            )

        return fired

    @property
    def stats(self) -> dict:
        return dict(self._stats)


# ---------------------------------------------------------------------------
# CLI test runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    from utils.logger import setup_logging
    setup_logging(Path("logs"), "DEBUG")

    parser = argparse.ArgumentParser(
        description="Test Twilio / Africa's Talking alert channels"
    )
    parser.add_argument("--check",         action="store_true",
                        help="Print current configuration")
    parser.add_argument("--test-sms",      action="store_true",
                        help="Send a test SMS via Twilio")
    parser.add_argument("--test-call",     action="store_true",
                        help="Make a test voice call via Twilio")
    parser.add_argument("--test-whatsapp", action="store_true",
                        help="Send a test WhatsApp message via Twilio")
    parser.add_argument("--test-at",       action="store_true",
                        help="Send a test SMS via Africa's Talking")
    parser.add_argument("--test-all",      action="store_true",
                        help="Run all configured tests")
    args = parser.parse_args()

    if args.check or not any(vars(args).values()):
        print("\n=== Alert Channel Configuration ===\n")
        print(f"  TWILIO")
        print(f"    Enabled:      {alert_cfg.TWILIO_ENABLED}")
        sid_ok = alert_cfg.TWILIO_ACCOUNT_SID and not alert_cfg.TWILIO_ACCOUNT_SID.startswith('ACxxx')
        tok_ok = alert_cfg.TWILIO_AUTH_TOKEN and alert_cfg.TWILIO_AUTH_TOKEN != 'your_auth_token_here'
        print(f"    Account SID:  {'[OK]' if sid_ok else '[!!] NOT SET'}")
        print(f"    Auth Token:   {'[OK]' if tok_ok else '[!!] NOT SET'}")
        print(f"    From Number:  {alert_cfg.TWILIO_FROM_NUMBER or '[!!] not set'}")
        print(f"    To Numbers:   {alert_cfg.to_numbers or '[!!] not set'}")
        print(f"    SMS:          {alert_cfg.TWILIO_SMS_ENABLED} (on: {alert_cfg.SMS_ON_LEVELS})")
        print(f"    Voice:        {alert_cfg.TWILIO_VOICE_ENABLED} (on: {alert_cfg.CALL_ON_LEVELS})")
        print(f"    WhatsApp:     {alert_cfg.TWILIO_WHATSAPP_ENABLED} (on: {alert_cfg.WHATSAPP_ON_LEVELS})")
        print(f"\n  AFRICA'S TALKING")
        print(f"    Enabled:      {alert_cfg.AFRICASTALKING_ENABLED}")
        at_ok = alert_cfg.AFRICASTALKING_API_KEY and alert_cfg.AFRICASTALKING_API_KEY != 'your_api_key_here'
        print(f"    API Key:      {'[OK]' if at_ok else '[!!] NOT SET'}")
        print(f"    Username:     {alert_cfg.AFRICASTALKING_USERNAME}")
        print()
        if not any(vars(args).values()):
            print("Run with --test-sms, --test-call, --test-whatsapp, or --test-all")

    alerter = MultiChannelAlerter()

    if args.test_sms or args.test_all:
        print("\nTesting Twilio SMS…")
        ok = alerter.twilio.test_sms() if alerter.twilio.ready else False
        print("✅ SMS sent!" if ok else "❌ SMS failed (check logs)")

    if args.test_call or args.test_all:
        print("\nTesting Twilio Voice Call…")
        ok = alerter.twilio.test_call() if alerter.twilio.ready else False
        print("✅ Call placed!" if ok else "❌ Call failed (check logs)")

    if args.test_whatsapp or args.test_all:
        print("\nTesting Twilio WhatsApp…")
        ok = alerter.twilio.test_whatsapp() if alerter.twilio.ready else False
        print("✅ WhatsApp sent!" if ok else "❌ WhatsApp failed (check logs)")

    if args.test_at or args.test_all:
        print("\nTesting Africa's Talking SMS…")
        ok = alerter.at.test_sms() if alerter.at.ready else False
        print("✅ AT SMS sent!" if ok else "❌ AT SMS failed (check logs)")
