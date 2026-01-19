"""
PDF Generation Service

Handles certificate PDF generation using template overlay approach.
Uses ReportLab for text layer creation and PyPDF for merging with template.
"""

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from pypdf import PdfReader, PdfWriter


# Template path
TEMPLATE_PATH = Path(__file__).parent.parent / "resources" / "certificate.pdf"

# ==============================================================================
# COORDINATE CONFIGURATION
# Adjust these values to calibrate text positions on the template.
# All values are in points (1 inch = 72 points).
# Origin (0, 0) is at the BOTTOM-LEFT of the page.
# Standard A4 Landscape = 842 x 595 points
# ==============================================================================

# Page dimensions (A4 Landscape)
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)  # 842 x 595 points

# --- Text Color ---
# Pure White (#FFFFFF) to match dark certificate background
TEXT_COLOR_RGB = (1, 1, 1)

# --- Student Name ---
# Position: Right-of-center, beside "OF COMPLETION OF" label
STUDENT_NAME_X = 550                  # ADJUST: Right of center (was width/2)
STUDENT_NAME_Y = 380                  # ADJUST: Move up/down (was 320)
STUDENT_NAME_FONT = "Helvetica-Bold"
STUDENT_NAME_SIZE = 30

# --- Course Name ---
# Position: Centered, on the divider line above "In recognition..." paragraph
COURSE_NAME_Y = 295                   # ADJUST: Move up/down (was 260)
COURSE_NAME_FONT = "Helvetica-Bold"
COURSE_NAME_SIZE = 24

# --- Date ---
# Position: Centered over the "DATE" line (bottom left)
DATE_X = 200                          # Centered over left line
DATE_Y = 160                          # On the line
DATE_FONT = "Helvetica"
DATE_SIZE = 12

# --- Presented By ---
# Position: Centered over the "PRESENTED BY" line (bottom right)
PRESENTED_BY_X = 640                  # Centered over right line
PRESENTED_BY_Y = 160                  # On the line
PRESENTED_BY_FONT = "Helvetica"
PRESENTED_BY_SIZE = 12
PRESENTED_BY_TEXT = "Credlyse Team"

# --- Certificate ID ---
# Position: After "CERTIFICATE ID:" label in footer
CERT_ID_X = 300                       # ADJUST: After label (moved left from 330)
CERT_ID_Y = 75                        # ADJUST: Just above underline (moved up from 70)
CERT_ID_FONT = "Helvetica"
CERT_ID_SIZE = 12

# ==============================================================================


class PdfGenerator:
    """
    Service for generating certificate PDFs.
    
    Uses a two-step approach:
    1. Create a text layer PDF with dynamic content using ReportLab.
    2. Merge the text layer onto the template PDF using PyPDF.
    """
    
    @classmethod
    def generate_overlay(
        cls,
        student_name: str,
        course_name: str,
        issue_date: str,
        cert_id: str,
    ) -> BytesIO:
        """
        Generate a certificate PDF by overlaying text on the template.
        
        Args:
            student_name: Full name of the student.
            course_name: Title of the completed course.
            issue_date: Formatted date string (e.g., "January 19, 2026").
            cert_id: Unique certificate identifier (UUID string).
            
        Returns:
            BytesIO stream containing the final merged PDF.
        """
        # Step 1: Create text layer
        text_layer = cls._create_text_layer(
            student_name=student_name,
            course_name=course_name,
            issue_date=issue_date,
            cert_id=cert_id,
        )
        
        # Step 2: Merge with template
        merged_pdf = cls._merge_with_template(text_layer)
        
        return merged_pdf
    
    @classmethod
    def _create_text_layer(
        cls,
        student_name: str,
        course_name: str,
        issue_date: str,
        cert_id: str,
    ) -> BytesIO:
        """
        Create a transparent PDF with only the dynamic text content.
        
        This PDF will be overlaid on the template.
        """
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=landscape(A4))
        width = PAGE_WIDTH
        
        # --- Set Pure White Text Color ---
        c.setFillColorRGB(*TEXT_COLOR_RGB)
        
        # --- Student Name (Right-of-Center) ---
        c.setFont(STUDENT_NAME_FONT, STUDENT_NAME_SIZE)
        c.drawCentredString(STUDENT_NAME_X, STUDENT_NAME_Y, student_name)
        
        # --- Course Name (Centered) ---
        c.setFont(COURSE_NAME_FONT, COURSE_NAME_SIZE)
        c.drawCentredString(width / 2, COURSE_NAME_Y, course_name)
        
        # --- Date (Centered over left line) ---
        c.setFont(DATE_FONT, DATE_SIZE)
        c.drawCentredString(DATE_X, DATE_Y, issue_date)
        
        # --- Presented By (Centered over right line) ---
        c.setFont(PRESENTED_BY_FONT, PRESENTED_BY_SIZE)
        c.drawCentredString(PRESENTED_BY_X, PRESENTED_BY_Y, PRESENTED_BY_TEXT)
        
        # --- Certificate ID (After label in footer) ---
        c.setFont(CERT_ID_FONT, CERT_ID_SIZE)
        # Show first 8 characters of UUID for brevity
        short_id = cert_id[:8] if len(cert_id) > 8 else cert_id
        c.drawString(CERT_ID_X, CERT_ID_Y, short_id)
        
        c.save()
        buffer.seek(0)
        return buffer
    
    @classmethod
    def _merge_with_template(cls, text_layer: BytesIO) -> BytesIO:
        """
        Merge the text layer PDF onto the template.
        
        Args:
            text_layer: BytesIO stream of the text-only PDF.
            
        Returns:
            BytesIO stream of the merged PDF.
        """
        # Read template
        template_reader = PdfReader(str(TEMPLATE_PATH))
        template_page = template_reader.pages[0]
        
        # Read text layer
        text_reader = PdfReader(text_layer)
        text_page = text_reader.pages[0]
        
        # Merge: overlay text layer onto template
        template_page.merge_page(text_page)
        
        # Write to output
        writer = PdfWriter()
        writer.add_page(template_page)
        
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        return output
