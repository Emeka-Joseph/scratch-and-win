import base64
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def qr_png(data, fill="#000000", back="#FFFFFF", box_size=10, border=2):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill, back_color=back)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_data_uri(data, **kw):
    return "data:image/png;base64," + base64.b64encode(qr_png(data, **kw)).decode()
