"""Alert email through Gmail SMTP (same approach as the News Tracker). Secrets come from the environment only:
GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO. Nothing about the recipient is stored in the repository."""
import os, smtplib, ssl, sys
from email.mime.text import MIMEText
from email.utils import formataddr


def send(subject, body):
    user, pw, to = os.environ.get("GMAIL_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip(), os.environ.get("ALERT_TO", "").strip()
    if not (user and pw and to):
        print("ALERT (email not configured, printed only):", subject, "\n", body)
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[GASTAT monitor] {subject}"; msg["From"] = formataddr(("GASTAT Data Monitor", user)); msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(user, pw); s.sendmail(user, [to], msg.as_string())
    print("alert sent:", subject)
    return True


if __name__ == "__main__":   # python -m gastat.alert "subject" "body"
    send(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
