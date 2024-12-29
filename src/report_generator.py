from typing import List, Dict
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image as PILImage
from io import BytesIO
from .config import REPORT_OUTPUT_DIR

class ReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
    
    def generate_report(self, matches: List[Dict]) -> str:
        """
        Generate a PDF report of matched transactions
        Args:
            matches: List of matched records with check images
        Returns:
            Path to the generated report
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(REPORT_OUTPUT_DIR, f'billing_matches_{timestamp}.pdf')
        
        doc = SimpleDocTemplate(report_path, pagesize=letter)
        story = []
        
        # Add title
        title = Paragraph("Billing Match Report", self.styles['Title'])
        story.append(title)
        story.append(Spacer(1, 20))
        
        # Add matches
        for match in matches:
            story.extend(self._create_match_section(match))
            story.append(Spacer(1, 30))
        
        doc.build(story)
        return report_path
    
    def _create_match_section(self, match: Dict) -> List:
        """Create a section for a single match"""
        elements = []
        
        # Match header
        header = Paragraph(f"Match (Confidence: {match['confidence_score']:.2%})", 
                         self.styles['Heading2'])
        elements.append(header)
        elements.append(Spacer(1, 10))
        
        # Transaction details
        transaction = match['transaction']
        knack_record = match['knack_record']
        
        data = [
            ['', 'Knack Record', 'Transaction'],
            ['Amount', f"${knack_record['amount']:.2f}", f"${transaction['amount']:.2f}"],
            ['Date', knack_record.get('date', 'N/A'), transaction.get('date', 'N/A')],
            ['Reference', knack_record.get('reference', 'N/A'), 
             transaction.get('reference', 'N/A')]
        ]
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
        elements.append(Spacer(1, 10))
        
        # Add check image if available
        if match.get('check_image'):
            try:
                img = PILImage.open(BytesIO(match['check_image']))
                img = img.convert('RGB')
                
                # Resize image to fit on page
                max_width = 400
                aspect = img.height / img.width
                img = img.resize((max_width, int(max_width * aspect)))
                
                # Save to temporary buffer
                img_buffer = BytesIO()
                img.save(img_buffer, format='JPEG')
                img_buffer.seek(0)
                
                # Add to report
                img = Image(img_buffer, width=max_width, height=int(max_width * aspect))
                elements.append(img)
            except Exception as e:
                elements.append(Paragraph(f"Error displaying check image: {str(e)}", 
                                       self.styles['Normal']))
        
        return elements
