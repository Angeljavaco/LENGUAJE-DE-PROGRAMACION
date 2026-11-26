from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


def build_donation_certificate(donation, issued_on):
    output = BytesIO()
    width, height = landscape(A4)
    pdf = Canvas(output, pagesize=(width, height))
    pdf.setTitle(f"Certificado de donación #{donation.id}")
    pdf.setAuthor("Desperdicio Cero")

    dark = HexColor("#17362D")
    green = HexColor("#23604B")
    muted = HexColor("#465D54")
    gold = HexColor("#B68C46")
    cream = HexColor("#FBF8EF")
    pale = HexColor("#EDF3ED")
    center = width / 2

    def label(value, x, y, size, color, font="Helvetica", centered=False):
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        if centered:
            pdf.drawCentredString(x, y, value)
        else:
            pdf.drawString(x, y, value)

    def fitted_text(value, x, top, box_width, box_height, size, font, centered=False):
        for font_size in range(size, 7, -1):
            style = ParagraphStyle(
                "certificate", fontName=font, fontSize=font_size,
                leading=font_size * 1.18, textColor=dark,
                alignment=TA_CENTER if centered else 0,
            )
            paragraph = Paragraph(escape(str(value)), style)
            _, text_height = paragraph.wrap(box_width, box_height)
            if text_height <= box_height:
                paragraph.drawOn(pdf, x, top - text_height)
                return
        raise ValueError("El texto excede el espacio del certificado.")

    pdf.setFillColor(cream)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(dark)
    pdf.setLineWidth(2)
    pdf.rect(24, 24, width - 48, height - 48, fill=0, stroke=1)
    pdf.setStrokeColor(gold)
    pdf.setLineWidth(0.7)
    pdf.rect(31, 31, width - 62, height - 62, fill=0, stroke=1)
    for y in (45, height - 45):
        pdf.line(48, y, 91, y)
        pdf.line(width - 91, y, width - 48, y)

    # Sello gráfico de recepción.
    pdf.setFillColor(pale)
    pdf.setStrokeColor(gold)
    pdf.circle(center, 511, 31, fill=1, stroke=1)
    pdf.setFillColor(green)
    pdf.circle(center, 511, 25, fill=1, stroke=0)
    pdf.setStrokeColor(cream)
    pdf.setLineWidth(3)
    pdf.setLineCap(1)
    pdf.lines([(center - 10, 510, center - 3, 503), (center - 3, 503, center + 11, 519)])

    label("DESPERDICIO CERO", center, 459, 11, green, "Helvetica-Bold", centered=True)
    label("Certificado de donación", center, 414, 42, dark, "Times-Bold", centered=True)
    label("Otorgado a", center, 377, 12, muted, centered=True)
    fitted_text(donation.food.donor.name, 92, 362, width - 184, 62, 30, "Times-Bold", centered=True)
    pdf.setStrokeColor(gold)
    pdf.setLineWidth(0.7)
    pdf.line(center - 112, 294, center + 112, 294)
    label("Por su aporte al rescate de alimentos y a la reducción del desperdicio.",
          center, 270, 12, muted, centered=True)
    label("La persona beneficiaria confirmó la recepción de esta donación.",
          center, 251, 12, muted, centered=True)

    panel_x = 78
    panel_width = width - 2 * panel_x
    pdf.setFillColor(pale)
    pdf.roundRect(panel_x, 134, panel_width, 83, 10, fill=1, stroke=0)
    quantity_x = panel_x + panel_width * 0.62
    pdf.setStrokeColor(gold)
    pdf.line(quantity_x, 148, quantity_x, 203)
    label("ALIMENTO DONADO", panel_x + 20, 194, 9, green, "Helvetica-Bold")
    label("CANTIDAD RECIBIDA", quantity_x + 20, 194, 9, green, "Helvetica-Bold")
    fitted_text(donation.food.name, panel_x + 20, 182, quantity_x - panel_x - 40, 38, 16, "Helvetica-Bold")
    fitted_text(f"{donation.quantity:g} {donation.food.unit}", quantity_x + 20, 182,
                panel_x + panel_width - quantity_x - 40, 38, 16, "Helvetica-Bold")

    label(f"Solicitud n.º {donation.id}", panel_x, 105, 10, dark, "Helvetica-Bold")
    pdf.setFillColor(dark)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(width - panel_x, 105, f"Emitido el {issued_on:%d/%m/%Y}")
    label("RECEPCIÓN CONFIRMADA", center, 71, 10, green, "Helvetica-Bold", centered=True)

    pdf.showPage()
    pdf.save()
    output.seek(0)
    return output
