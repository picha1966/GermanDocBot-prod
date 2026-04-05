import fitz
import sys
import os

def generate_grid(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found")
        return
    
    doc = fitz.open(pdf_path)
    for page in doc:
        width = page.rect.width
        height = page.rect.height
        # Малюємо сітку кожні 50 точок
        for x in range(0, int(width), 50):
            page.draw_line(fitz.Point(x, 0), fitz.Point(x, height), color=(1, 0, 0), width=0.5)
            page.insert_text((x + 2, 10), str(x), fontsize=8, color=(1, 0, 0))
        for y in range(0, int(height), 50):
            page.draw_line(fitz.Point(0, y), fitz.Point(width, y), color=(0, 0, 1), width=0.5)
            page.insert_text((5, y - 2), str(int(height - y)), fontsize=8, color=(0, 0, 1))
    
    output_path = pdf_path.replace(".pdf", "_grid.pdf")
    doc.save(output_path)
    print(f"✅ Успіх! Файл із сіткою створено: {output_path}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "backend/templates/anmeldung.pdf"
    generate_grid(path)