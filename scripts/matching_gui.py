import os
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QTreeWidget, 
                           QTreeWidgetItem, QFrame, QSizePolicy)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
import cv2
import numpy as np
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import io
import json
import os
from datetime import datetime

def normalize_amount(amount_str):
    """Convert amount string to float, handling $ and commas."""
    if isinstance(amount_str, (int, float)):
        return float(amount_str)
    if not amount_str:
        return 0.0
    return float(amount_str.replace('$', '').replace(',', ''))

class MatchingGUI(QMainWindow):
    def __init__(self, check_data, potential_matches):
        super().__init__()
        self.setWindowTitle("Check Matching Assistant")
        self.setGeometry(100, 100, 1200, 800)
        
        # Store data
        self.all_checks = check_data
        self.current_check_index = 0
        self.check_data = self.all_checks[self.current_check_index] if self.all_checks else None
        self.potential_matches = potential_matches
        self.selected_match = None
        self.final_matches = []
        self.current_image = None  # Store the original image
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Left side - Check image and details
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Image container that will scale with window
        image_container = QWidget()
        image_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        
        # Check image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setMinimumSize(500, 300)
        image_layout.addWidget(self.image_label)
        
        left_layout.addWidget(image_container, stretch=1)  # Give it most of the vertical space
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        prev_button = QPushButton("Previous")
        prev_button.clicked.connect(self.prev_check)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_check)
        nav_layout.addWidget(prev_button)
        nav_layout.addWidget(QLabel("Check"))
        nav_layout.addWidget(next_button)
        left_layout.addLayout(nav_layout)
        
        # Check details
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        left_layout.addWidget(self.details_label)
        
        layout.addWidget(left_frame)
        
        # Right side - Potential matches
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        
        # Matches tree
        self.matches_tree = QTreeWidget()
        self.matches_tree.setHeaderLabels(["Name", "Confidence", "Amount", "Date"])
        self.matches_tree.setColumnWidth(0, 200)
        right_layout.addWidget(self.matches_tree)
        
        # Buttons
        button_layout = QHBoxLayout()
        confirm_button = QPushButton("Confirm Match")
        confirm_button.clicked.connect(self.confirm_match)
        skip_button = QPushButton("Skip Check")
        skip_button.clicked.connect(self.skip_check)
        finish_button = QPushButton("Finish")
        finish_button.clicked.connect(self.finish)
        button_layout.addWidget(confirm_button)
        button_layout.addWidget(skip_button)
        button_layout.addWidget(finish_button)
        right_layout.addLayout(button_layout)
        
        layout.addWidget(right_frame)
        
        # Load initial check
        self.load_current_check()
    
    def load_current_check(self):
        if not self.check_data:
            return
            
        # Update check details
        amount = normalize_amount(self.check_data.get('amount', 0))
        check_details = f"Check Details:\n"
        check_details += f"Amount: ${amount:,.2f}\n"
        check_details += f"Date: {self.check_data.get('date', 'N/A')}\n"
        check_details += f"From: {self.check_data.get('from', 'N/A')}"
        self.details_label.setText(check_details)
        
        # Load check image
        self.load_check_image()
        
        # Update matches tree
        self.matches_tree.clear()
        current_matches = self.potential_matches[self.current_check_index] if self.current_check_index < len(self.potential_matches) else []
        
        # Auto-select the highest confidence match
        highest_confidence = 0
        highest_confidence_item = None
        
        for match in current_matches:
            invoice = match['invoice']
            confidence = match['confidence']
            
            item = QTreeWidgetItem([
                invoice['payee'],
                f"{confidence:.1%}",
                f"${normalize_amount(invoice['amount']):,.2f}",
                invoice['date']
            ])
            self.matches_tree.addTopLevelItem(item)
            
            if confidence > highest_confidence:
                highest_confidence = confidence
                highest_confidence_item = item
        
        # Select the highest confidence match
        if highest_confidence_item:
            highest_confidence_item.setSelected(True)
            self.matches_tree.setCurrentItem(highest_confidence_item)
    
    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)
        if self.current_image is not None:
            self.update_image_display()
    
    def update_image_display(self):
        """Update the image display based on current label size"""
        if self.current_image is None:
            return
            
        # Get the size of the label
        label_size = self.image_label.size()
        
        # Scale the image to fit the label while maintaining aspect ratio
        scaled_pixmap = self.current_image.scaled(
            label_size.width(), 
            label_size.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        self.image_label.setPixmap(scaled_pixmap)
    
    def load_check_image(self):
        """Load and display the check image."""
        try:
            # Get the PNG path from the check data
            png_path = self.check_data.get('png_path')
            print(f"Loading image from: {png_path}")
            
            if not png_path:
                raise ValueError("No PNG path found in check data")
            
            if not os.path.exists(png_path):
                raise FileNotFoundError(f"PNG file not found: {png_path}")
            
            print(f"Image file exists: {os.path.getsize(png_path)} bytes")
            
            # Read image with OpenCV
            img = cv2.imread(png_path)
            if img is None:
                raise ValueError("Failed to load image with OpenCV")
                
            # Convert from BGR to RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Convert to QImage and then to QPixmap
            height, width, channel = img.shape
            bytes_per_line = 3 * width
            q_img = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Store the original image
            self.current_image = QPixmap.fromImage(q_img)
            
            # Update the display
            self.update_image_display()
            print("Image configured in label")
            
        except Exception as e:
            print(f"Error loading check image: {e}")
            self.image_label.setText(f"Error loading check image: {e}")
            self.current_image = None
    
    def prev_check(self):
        if self.current_check_index > 0:
            self.current_check_index -= 1
            self.check_data = self.all_checks[self.current_check_index]
            self.load_current_check()
    
    def next_check(self):
        if self.current_check_index < len(self.all_checks) - 1:
            self.current_check_index += 1
            self.check_data = self.all_checks[self.current_check_index]
            self.load_current_check()
    
    def confirm_match(self):
        selected_items = self.matches_tree.selectedItems()
        if selected_items:
            selected_index = self.matches_tree.indexOfTopLevelItem(selected_items[0])
            current_matches = self.potential_matches[self.current_check_index]
            self.final_matches.append({
                'check': self.check_data,
                'invoice': current_matches[selected_index]['invoice']
            })
            self.next_check()
    
    def skip_check(self):
        self.final_matches.append({
            'check': self.check_data,
            'invoice': None
        })
        self.next_check()
    
    def finish(self):
        self.close()

def show_matching_gui(check_data, potential_matches):
    """Show GUI for manual matching and return selected match."""
    app = QApplication(sys.argv)
    gui = MatchingGUI(check_data, potential_matches)
    gui.show()
    app.exec_()
    return gui.final_matches
