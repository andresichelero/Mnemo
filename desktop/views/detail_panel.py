import customtkinter as ctk
import io
import json
from PIL import Image

class DetailPanel(ctk.CTkFrame):
    def __init__(self, master, client, **kwargs):
        super().__init__(master, width=350, corner_radius=0, **kwargs)
        self.client = client
        self.current_screenshot = None
        
        self.pack_propagate(False)
        self.grid_propagate(False)
        
        self.scrollable = ctk.CTkScrollableFrame(self)
        self.scrollable.pack(expand=True, fill="both", padx=5, pady=5)
        
        # Image preview
        self.img_label = ctk.CTkLabel(self.scrollable, text="Select an image")
        self.img_label.pack(pady=10)
        
        # Fonts
        title_font = ctk.CTkFont(family="Inter", size=16, weight="bold")
        label_font = ctk.CTkFont(family="Inter", size=12, weight="bold")
        text_font = ctk.CTkFont(family="Inter", size=12)

        # Details
        self.title_label = ctk.CTkLabel(self.scrollable, text="", font=title_font)
        self.title_label.pack(pady=(15, 5), anchor="w", padx=5)
        
        self.desc_textbox = ctk.CTkTextbox(self.scrollable, height=120, wrap="word", font=text_font, fg_color=("gray85", "gray17"))
        self.desc_textbox.pack(fill="x", pady=5, padx=5)
        self.desc_textbox.configure(state="disabled")
        
        # Tags & Category
        self.cat_label = ctk.CTkLabel(self.scrollable, text="Category: ", font=label_font, text_color=("gray20", "gray80"))
        self.cat_label.pack(anchor="w", pady=(10, 0), padx=5)
        
        self.tags_label = ctk.CTkLabel(self.scrollable, text="Tags: ", font=label_font, text_color=("gray20", "gray80"))
        self.tags_label.pack(anchor="w", pady=(5, 10), padx=5)
        
        self.text_textbox = ctk.CTkTextbox(self.scrollable, height=100, wrap="word", font=text_font, fg_color=("gray85", "gray17"))
        self.text_textbox.pack(fill="x", pady=5, padx=5)
        self.text_textbox.configure(state="disabled")
        
        # Actions
        self.analyze_btn = ctk.CTkButton(self.scrollable, text="Re-analyze", command=self._reanalyze)
        self.analyze_btn.pack(fill="x", pady=5)
        
        self.open_btn = ctk.CTkButton(self.scrollable, text="Open File", command=self._open_file)
        self.open_btn.pack(fill="x", pady=5)
        
        # Move to folder section
        self.folder_var = ctk.StringVar(value="Select Folder")
        self.folder_dropdown = ctk.CTkOptionMenu(self.scrollable, variable=self.folder_var, values=["Select Folder"])
        self.folder_dropdown.pack(fill="x", pady=(15, 5))
        
        self.move_btn = ctk.CTkButton(self.scrollable, text="Assign to Folder", command=self._move_to_folder)
        self.move_btn.pack(fill="x", pady=5)
        
    def load_item(self, screenshot_data):
        self.current_screenshot = screenshot_data
        
        # Load high-res image if possible, but thumbnail is faster for now
        self.img_label.configure(text="Loading...")
        self.after(50, self._load_image)
        
        # Update text
        self.title_label.configure(text=screenshot_data.get("original_filename", "Unknown"))
        
        # Fetch detailed analysis if available
        self.desc_textbox.configure(state="normal")
        self.desc_textbox.delete("1.0", "end")
        self.desc_textbox.insert("1.0", "Loading...")
        self.desc_textbox.configure(state="disabled")
        
        self.text_textbox.configure(state="normal")
        self.text_textbox.delete("1.0", "end")
        self.text_textbox.configure(state="disabled")

        def fetch():
            detailed = self.client.get_screenshot(screenshot_data["id"])
            folders_res = self.client.get_folders()
            self.after(0, lambda: self._update_details(detailed, folders_res))
            
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def _update_details(self, detailed, folders_res):
        self.desc_textbox.configure(state="normal")
        self.desc_textbox.delete("1.0", "end")
        self.text_textbox.configure(state="normal")
        self.text_textbox.delete("1.0", "end")
        
        if "error" not in detailed and detailed.get("analysis"):
            analysis = detailed["analysis"]
            self.desc_textbox.insert("1.0", analysis.get("description", "No description."))
            
            self.cat_label.configure(text=f"Category: {analysis.get('category', 'unknown')}")
            
            tags = analysis.get("tags", [])
            if isinstance(tags, str):
                try:
                    import json
                    tags = json.loads(tags)
                except:
                    pass
            self.tags_label.configure(text=f"Tags: {', '.join(tags)}")
            
            extracted = analysis.get("extracted_text", "")
            if extracted:
                self.text_textbox.insert("1.0", f"Extracted text:\n{extracted}")
            else:
                self.text_textbox.insert("1.0", "No extracted text.")
                
        else:
            self.desc_textbox.insert("1.0", "No analysis available.")
            self.text_textbox.insert("1.0", "")
            self.cat_label.configure(text="Category: None")
            self.tags_label.configure(text="Tags: None")
            
        self.desc_textbox.configure(state="disabled")
        self.text_textbox.configure(state="disabled")

        # Populate folders
        if "error" not in folders_res and isinstance(folders_res, list):
            self.available_folders = {f["name"]: f["id"] for f in folders_res}
            names = list(self.available_folders.keys())
            if names:
                self.folder_dropdown.configure(values=names)
                # Select the first assigned folder if any
                assigned_folders = detailed.get("folders", [])
                if assigned_folders:
                    self.folder_var.set(assigned_folders[0]["name"])
                else:
                    self.folder_var.set("Select Folder")
            else:
                self.folder_dropdown.configure(values=["No folders"])
                self.folder_var.set("No folders")
        
    def _load_image(self):
        if not self.current_screenshot:
            return
            
        try:
            image_bytes = self.client.download_image(self.current_screenshot["id"], thumbnail=False)
            if image_bytes:
                image = Image.open(io.BytesIO(image_bytes))
                
                # Resize to fit width 300
                ratio = 300.0 / image.width
                new_size = (300, int(image.height * ratio))
                
                ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=new_size)
                self.img_label.configure(image=ctk_image, text="")
            else:
                self.img_label.configure(text="No Image")
        except Exception as e:
            self.img_label.configure(text="Error")
            
    def _reanalyze(self):
        if self.current_screenshot:
            self.analyze_btn.configure(state="disabled", text="Queued...")
            res = self.client.analyze_screenshot(self.current_screenshot["id"])
            if "error" not in res:
                # refresh status
                pass
            self.after(2000, lambda: self.analyze_btn.configure(state="normal", text="Re-analyze"))

    def _open_file(self):
        if not self.current_screenshot:
            return
        path = self.current_screenshot.get("file_path")
        if path:
            import os
            import sys
            import subprocess
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                # Check for WSL
                is_wsl = False
                try:
                    with open('/proc/version', 'r') as f:
                        if 'microsoft' in f.read().lower():
                            is_wsl = True
                except:
                    pass
                    
                if is_wsl:
                    try:
                        # Try wslview first
                        subprocess.run(["wslview", path], check=True)
                    except:
                        # Fallback to explorer.exe using wslpath
                        try:
                            win_path = subprocess.check_output(["wslpath", "-w", path]).decode().strip()
                            subprocess.run(["explorer.exe", win_path])
                        except:
                            print(f"Failed to open in WSL. Path: {path}")
                else:
                    subprocess.run(["xdg-open", path])

    def _move_to_folder(self):
        if not self.current_screenshot or not hasattr(self, 'available_folders'):
            return
            
        name = self.folder_var.get()
        if name in self.available_folders:
            folder_id = self.available_folders[name]
            def assign():
                self.client.update_screenshot_folders(self.current_screenshot["id"], [folder_id])
                self.after(0, lambda: self.move_btn.configure(text="Assigned!"))
                self.after(2000, lambda: self.move_btn.configure(text="Assign to Folder"))
            
            self.move_btn.configure(text="Assigning...")
            import threading
            threading.Thread(target=assign, daemon=True).start()
