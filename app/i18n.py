"""Customer-facing translations (English / Arabic)."""
from flask import session

LANGS = ("en", "ar")

STRINGS = {
    "choose_language": {"en": "Choose your language", "ar": "اختر لغتك"},
    "continue": {"en": "Continue", "ar": "متابعة"},
    "welcome": {"en": "Welcome to", "ar": "أهلاً بك في"},
    "scratch_win": {"en": "Scratch & Win", "ar": "اكشط واربح"},
    "hero_sub": {"en": "Register in seconds, verify your email and scratch to reveal your guaranteed gift.",
                 "ar": "سجّل خلال ثوانٍ، وأكّد بريدك الإلكتروني، ثم اكشط لتكشف عن هديتك المضمونة."},
    "full_name": {"en": "Full name", "ar": "الاسم الكامل"},
    "mobile": {"en": "Mobile number", "ar": "رقم الجوال"},
    "email": {"en": "Email address", "ar": "البريد الإلكتروني"},
    "accept_terms_pre": {"en": "I have read and accept the", "ar": "لقد قرأت وأوافق على"},
    "terms": {"en": "Terms & Conditions", "ar": "الشروط والأحكام"},
    "marketing": {"en": "Send me offers and news (optional)", "ar": "أرسلوا لي العروض والأخبار (اختياري)"},
    "submit": {"en": "Submit", "ar": "إرسال"},
    "min_spend_note": {"en": "Valid for qualifying bills of {amount} or more.",
                       "ar": "صالح للفواتير المؤهلة بقيمة {amount} أو أكثر."},
    "one_per_customer": {"en": "One gift per customer. Your email and mobile number can be used only once.",
                         "ar": "هدية واحدة لكل عميل. يمكن استخدام بريدك الإلكتروني ورقم جوالك مرة واحدة فقط."},
    "err_name": {"en": "Please enter your full name.", "ar": "يرجى إدخال اسمك الكامل."},
    "err_email": {"en": "Please enter a valid email address.", "ar": "يرجى إدخال بريد إلكتروني صحيح."},
    "err_mobile": {"en": "Please enter a valid mobile number.", "ar": "يرجى إدخال رقم جوال صحيح."},
    "err_terms": {"en": "You must accept the Terms & Conditions.", "ar": "يجب الموافقة على الشروط والأحكام."},
    "err_already": {"en": "This email or mobile number has already taken part in this promotion. It's one gift per customer.",
                    "ar": "سبق أن شارك هذا البريد الإلكتروني أو رقم الجوال في هذا العرض. هدية واحدة فقط لكل عميل."},
    "verify_title": {"en": "Check your inbox", "ar": "تحقّق من بريدك"},
    "verify_sub": {"en": "We sent a 7-character code to", "ar": "أرسلنا رمزاً من 7 خانات إلى"},
    "verify_hint": {"en": "Letters and numbers, not case-sensitive. Check spam if you don't see it.",
                    "ar": "حروف وأرقام، لا يهم حالة الأحرف. تحقق من مجلد الرسائل غير المرغوبة إن لم تجده."},
    "verify_btn": {"en": "Verify & play", "ar": "تحقّق والعب"},
    "resend": {"en": "Resend code", "ar": "إعادة إرسال الرمز"},
    "resend_in": {"en": "Resend in", "ar": "إعادة الإرسال خلال"},
    "err_email_send": {"en": "We couldn't send the email just now. Check your email address, wait a moment and tap Resend code, or ask a staff member for help.",
                       "ar": "تعذّر إرسال البريد الإلكتروني الآن. تحقق من بريدك الإلكتروني وانتظر قليلاً ثم اضغط إعادة إرسال الرمز، أو اطلب المساعدة من أحد الموظفين."},
    "code_resent": {"en": "A new code is on its way.", "ar": "تم إرسال رمز جديد."},
    "err_code": {"en": "That code is incorrect. Attempts left: {n}", "ar": "الرمز غير صحيح. المحاولات المتبقية: {n}"},
    "err_code_expired": {"en": "This code has expired. Please request a new one.", "ar": "انتهت صلاحية الرمز. يرجى طلب رمز جديد."},
    "err_code_locked": {"en": "Too many wrong attempts. Please request a new code.",
                        "ar": "محاولات خاطئة كثيرة. يرجى طلب رمز جديد."},
    "err_resend_wait": {"en": "Please wait a moment before requesting another code.",
                        "ar": "يرجى الانتظار قليلاً قبل طلب رمز آخر."},
    "err_resend_limit": {"en": "Too many codes requested. Please ask a staff member for help.",
                         "ar": "تم طلب رموز كثيرة. يرجى طلب المساعدة من أحد الموظفين."},
    "change_email": {"en": "Wrong email? Start again", "ar": "بريد خاطئ؟ ابدأ من جديد"},
    "scratch_title": {"en": "Scratch to reveal your gift", "ar": "اكشط لتكشف عن هديتك"},
    "scratch_sub": {"en": "Use your finger to wipe the silver surface.", "ar": "استخدم إصبعك لمسح السطح الفضي."},
    "scratch_here": {"en": "SCRATCH HERE", "ar": "اكشط هنا"},
    "congrats": {"en": "Congratulations!", "ar": "مبروك!"},
    "you_won": {"en": "You won", "ar": "لقد ربحت"},
    "claim_code": {"en": "Claim code", "ar": "رمز المطالبة"},
    "show_staff": {"en": "Show this QR code to a staff member to collect your gift.",
                   "ar": "اعرض رمز QR هذا على أحد الموظفين لاستلام هديتك."},
    "valid_until": {"en": "Valid until", "ar": "صالح حتى"},
    "email_copy": {"en": "We've also emailed this to you.", "ar": "أرسلنا لك نسخة عبر البريد الإلكتروني أيضاً."},
    "status_redeemed": {"en": "Redeemed — enjoy your gift!", "ar": "تم الاستلام — استمتع بهديتك!"},
    "status_expired": {"en": "This gift has expired.", "ar": "انتهت صلاحية هذه الهدية."},
    "closed_title": {"en": "This promotion isn't running right now", "ar": "هذا العرض غير متاح حالياً"},
    "closed_sub": {"en": "Please check with our staff for current offers.", "ar": "يرجى مراجعة موظفينا لمعرفة العروض الحالية."},
    "sold_out_title": {"en": "All gifts have been claimed", "ar": "تم توزيع جميع الهدايا"},
    "sold_out_sub": {"en": "Thank you for your interest. Stay tuned for our next promotion!",
                     "ar": "شكراً لاهتمامك. ترقّب عرضنا القادم!"},
    "close": {"en": "Close", "ar": "إغلاق"},
    "powered_by": {"en": "Part of", "ar": "جزء من"},
    "language": {"en": "العربية", "ar": "English"},
    "save_screenshot": {"en": "Tip: take a screenshot of this screen.", "ar": "نصيحة: التقط صورة لهذه الشاشة."},
    "email_verify_subject": {"en": "Your {brand} code: {code}", "ar": "رمزك من {brand}: {code}"},
    "email_verify_body": {"en": "Use this code to verify your email and play Scratch & Win:",
                          "ar": "استخدم هذا الرمز لتأكيد بريدك الإلكتروني واللعب في اكشط واربح:"},
    "email_verify_expiry": {"en": "The code expires in {m} minutes. If you didn't request it, ignore this email.",
                            "ar": "تنتهي صلاحية الرمز خلال {m} دقيقة. إن لم تطلبه، تجاهل هذه الرسالة."},
    "email_prize_subject": {"en": "You won at {brand}: {prize}", "ar": "ربحت في {brand}: {prize}"},
    "hello": {"en": "Hello", "ar": "مرحباً"},
}


def get_lang():
    lang = session.get("lang", "en")
    return lang if lang in LANGS else "en"


def t(key, lang=None, **kw):
    lang = lang or get_lang()
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry["en"]
    return text.format(**kw) if kw else text
