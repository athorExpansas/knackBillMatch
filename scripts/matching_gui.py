import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import io
import json
import os
from datetime import datetime

def normalize_amount(amount):
    """Convert amount string to float, handling $ and commas."""
    if isinstance(amount, (int, float)):
        return float(amount)
    return float(amount.replace('$', '').replace(',', ''))

class MatchingGUI:
    def __init__(self, check_data, potential_matches):
        self.root = tk.Tk()
        self.root.title("Check Matching Assistant")
        self.root.geometry("1200x800")
        
        self.check_data = check_data
        self.potential_matches = potential_matches
        self.selected_match = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Left side - Check image and details
        left_frame = ttk.Frame(self.root)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Check image
        self.image_label = ttk.Label(left_frame)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        self.load_check_image()
        
        # Check details
        check_details = f"Check #{self.check_data.get('check_number', 'N/A')}\n"
        amount = normalize_amount(self.check_data.get('amount', '0'))
        check_details += f"Amount: ${amount:,.2f}\n"
        check_details += f"Date: {self.check_data.get('date', 'N/A')}\n"
        check_details += f"From: {self.check_data.get('from', 'N/A')}"
        
        ttk.Label(left_frame, text=check_details, justify=tk.LEFT).pack(pady=10)
        
        # Right side - Potential matches
        right_frame = ttk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(right_frame, text="Potential Matches:").pack()
        
        # Treeview for matches
        columns = ('invoice_number', 'amount', 'date', 'payee')
        self.tree = ttk.Treeview(right_frame, columns=columns, show='headings')
        
        self.tree.heading('invoice_number', text='Invoice Number')
        self.tree.heading('amount', text='Amount')
        self.tree.heading('date', text='Date')
        self.tree.heading('payee', text='Payee')
        
        self.tree.column('invoice_number', width=120)
        self.tree.column('amount', width=100)
        self.tree.column('date', width=100)
        self.tree.column('payee', width=200)
        
        for match in self.potential_matches:
            self.tree.insert('', tk.END, values=(
                match['invoice_number'],
                f"${normalize_amount(match['amount']):,.2f}",
                match['date'],
                match['payee']
            ))
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="Select Match", command=self.on_select).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="No Match", command=self.on_no_match).pack(side=tk.LEFT, padx=5)
        
    def load_check_image(self):
        """Load and display the check image."""
        try:
            image_path = self.check_data.get('image_path')
            if not image_path or not os.path.exists(image_path):
                self.image_label.configure(text="Check image not available")
                return
                
            # Open PDF with PyMuPDF
            doc = fitz.open(image_path)
            page = doc[0]
            
            # Convert to PIL Image
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # Resize to fit window (maintaining aspect ratio)
            display_size = (500, 300)
            img.thumbnail(display_size, Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)
            self.image_label.configure(image=photo)
            self.image_label.image = photo  # Keep a reference
            
            # Close the document
            doc.close()
            
        except Exception as e:
            print(f"Error loading check image: {e}")
            self.image_label.configure(text=f"Error loading check image: {e}")
    
    def on_select(self):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            invoice_number = item['values'][0]
            self.selected_match = next(m for m in self.potential_matches if m['invoice_number'] == invoice_number)
        self.root.quit()
    
    def on_no_match(self):
        self.selected_match = None
        self.root.quit()
    
    def run(self):
        self.root.mainloop()
        self.root.destroy()
        return self.selected_match

def show_matching_gui(check_data, potential_matches):
    """Show GUI for manual matching and return selected match."""
    gui = MatchingGUI(check_data, potential_matches)
    return gui.run()
