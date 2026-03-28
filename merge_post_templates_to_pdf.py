import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# Ask user for folder path
folder_path = input("📁 Enter the path to the folder with .txt files: ").strip()

# Validate path
if not os.path.isdir(folder_path):
    print(f"❌ Folder not found: {folder_path}")
    exit(1)

# Use folder name as PDF filename
folder_name = os.path.basename(os.path.normpath(folder_path))
output_pdf_path = os.path.join(folder_path, f"{folder_name}.pdf")

# PDF layout setup
page_width, page_height = A4
margin = inch * 0.75
line_height = 14
max_lines_per_page = int((page_height - 2 * margin) / line_height)

# Start the PDF
c = canvas.Canvas(output_pdf_path, pagesize=A4)

def add_text_to_pdf(title, lines):
    y = page_height - margin
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, title)
    y -= line_height * 2
    c.setFont("Helvetica", 11)

    line_count = 0
    for line in lines:
        if line_count >= max_lines_per_page - 3:
            c.showPage()
            y = page_height - margin
            c.setFont("Helvetica", 11)
            line_count = 0
        c.drawString(margin, y, line.strip())
        y -= line_height
        line_count += 1

    # Add a page break after each file
    c.showPage()

# Go through all .txt files
for filename in sorted(os.listdir(folder_path)):
    if filename.endswith(".txt"):
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            title = f"--- {filename} ---"
            add_text_to_pdf(title, lines)

# Save final PDF
c.save()
print(f"✅ PDF created: {output_pdf_path}")
