"""WhatsApp flow mock. State machine + chat simulator. Replies are classified by keywords (no LLM needed)."""
import re
from rto.engine import prepaid_offer

YES = re.compile(r"\b(yes|y|haan|han|ha|ok|okay|confirm|confirmed|theek|thik|sahi|1)\b", re.I)
NO = re.compile(r"\b(no|nahi|nahin|na|cancel|mat|nope|2)\b", re.I)

def confirm_msg(o):
    return (f"Namaste {o['name']} 🙏 Aapka order #{o['order_id']} (₹{o['value']}) ready hai.\n"
            f"Kya aap delivery ke liye confirm karte hain? Reply *YES* to confirm ya *NO* to cancel.")

def nudge_msg(o, offer):
    return (f"Namaste {o['name']} 🙏 Aapka order #{o['order_id']} (₹{o['value']}) ready hai.\n"
           f"Abhi online pay karein aur ₹{offer['discount']} ki chhoot paayein: sirf ₹{o['value']-offer['discount']}. "
            f"Reply *PAY* for payment link, ya *COD* to keep Cash on Delivery.")

class Conversation:
    """kind: CONFIRM or NUDGE. Time is in hours since first message."""
    def __init__(self, order, kind, p_rto, cfg):
        self.o, self.kind, self.cfg, self.t = order, kind, cfg, 0.0
        self.offer = prepaid_offer(p_rto, order["value"], cfg) if kind == "NUDGE" else None
        self.state, self.log, self.reminded = "WAITING", [], False
        self.say(confirm_msg(order) if kind == "CONFIRM" else nudge_msg(order, self.offer))

    def say(self, m): self.log.append(("bot", self.t, m))
    def end(self, state, msg=None):
        self.state = state
        if msg: self.say(msg)
        return state

    def reply(self, text):
        self.log.append(("customer", self.t, text))
        if self.state != "WAITING": return self.state
        txt = text.strip().lower()
        if self.kind == "CONFIRM":
            if YES.search(txt) and not NO.search(txt): return self.end("SHIP", "Shukriya! Order dispatch ho raha hai 🚚")
            if NO.search(txt): return self.end("CANCEL", "Theek hai, order cancel kar diya. Phir milte hain!")
        else:
            if "pay" in txt or YES.search(txt): return self.end("PREPAID_LINK", "Payment link: https://pay.example/xyz ✅ (valid 24h)")
            if "cod" in txt or NO.search(txt): return self.end("SHIP_COD_CONFIRMED", "Theek hai, COD hi rakhte hain. Dispatch ho raha hai 🚚")
        # random reply: re-ask once, then hand to a human after 2 unclear
        self.unclear = getattr(self, "unclear", 0) + 1
        if self.unclear >= 2: return self.end("HUMAN_REVIEW", "Hamari team aapko call karegi 📞")
        self.say("Maaf kijiye, samajh nahi aaya. Please reply *YES* ya *NO*." if self.kind == "CONFIRM"
                 else "Please reply *PAY* ya *COD*.")
        return self.state

    def tick(self, hours):
        """Advance the clock; handles reminder and 24h silence."""
        self.t += hours
        w = self.cfg["whatsapp"]
        if self.state != "WAITING": return self.state
        if not self.reminded and self.t >= w["reminder_after_hours"]:
            self.reminded = True; self.say("Reminder: aapka order abhi hold par hai. Reply *YES* ya *NO* 🙏")
        if self.t >= w["expire_after_hours"]:
            # silence = strongest RTO signal. Confirm -> cancel; Nudge -> ship as COD only if risk was moderate.
            return self.end("CANCEL" if self.kind == "CONFIRM" else "SHIP_COD_UNCONFIRMED",
                            "Koi reply nahi mila, isliye order cancel kar rahe hain." if self.kind == "CONFIRM"
                            else "Aapka order COD par dispatch ho raha hai.")
        return self.state

if __name__ == "__main__":
    from rto.engine import load_cfg
    cfg = load_cfg(); o = {"name": "Priya", "order_id": "KT1", "value": 649}
    print("Chat simulator. Type replies; '/wait 24' skips hours; Ctrl-C to quit.")
    kind = input("flow [confirm/nudge]: ").strip().upper() or "CONFIRM"
    c = Conversation(o, "NUDGE" if kind.startswith("N") else "CONFIRM", 0.3, cfg); n = 0
    while True:
        for who, t, m in c.log[n:]: print(f"  [{t:>4.0f}h] BOT: {m}" if who == "bot" else "")
        n = len(c.log)
        if c.state != "WAITING": print("FINAL:", c.state); break
        x = input("you> ")
        if x.startswith("/wait"): c.tick(float(x.split()[1]))
        else: c.reply(x)
