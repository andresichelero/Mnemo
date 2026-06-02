import customtkinter as ctk
import io
from PIL import Image

class GalleryItem(ctk.CTkFrame):
    def __init__(self, master, screenshot_data, click_callback, client, **kwargs):
        super().__init__(master, width=200, height=250, corner_radius=10, **kwargs)
        self.screenshot_data = screenshot_data
        self.click_callback = click_callback
        self.client = client
        self.selected = False
        
        # Disable frame propagation so it stays 200x250
        self.grid_propagate(False)
        self.pack_propagate(False)
        
        # Better styling for items
        self.configure(fg_color=("gray90", "gray13"), border_width=1, border_color=("gray80", "gray20"))
        
        # Load thumbnail placeholder
        self.img_label = ctk.CTkLabel(self, text="Loading...", fg_color="transparent")
        self.img_label.pack(expand=True, fill="both", padx=10, pady=(10, 0))
        
        self.info_label = ctk.CTkLabel(self, text=screenshot_data.get("original_filename", "Unknown")[:20], 
                                      font=ctk.CTkFont(family="Inter", size=11, weight="bold"), text_color=("gray30", "gray70"))
        self.info_label.pack(side="bottom", pady=8)
        
        # Checkbox overlay with better positioning
        self.checkbox = ctk.CTkCheckBox(self, text="", width=24, height=24, corner_radius=6, border_width=2, command=self._on_checkbox_toggle)
        self.checkbox.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)
        
        # Bind clicks
        self.bind("<Button-1>", self._on_click)
        self.img_label.bind("<Button-1>", self._on_click)
        self.info_label.bind("<Button-1>", self._on_click)
        
        # Trigger async image load
        self.after(50, self._load_image)

    def _load_image(self):
        def fetch():
            try:
                image_bytes = self.client.download_image(self.screenshot_data["id"], thumbnail=True)
                if image_bytes:
                    image = Image.open(io.BytesIO(image_bytes))
                    ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(180, 180))
                    self.after(0, lambda: self.img_label.configure(image=ctk_image, text=""))
                else:
                    self.after(0, lambda: self.img_label.configure(text="No Image"))
            except Exception as e:
                self.after(0, lambda: self.img_label.configure(text="Error"))
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def _on_checkbox_toggle(self):
        if self.click_callback:
            self.click_callback(self.screenshot_data, is_checkbox=True, is_selected=bool(self.checkbox.get()))

    def _on_click(self, event):
        if self.click_callback:
            self.click_callback(self.screenshot_data, is_checkbox=False, is_selected=False)

    def set_selected(self, selected: bool):
        self.selected = selected
        if selected:
            self.configure(fg_color=("gray75", "gray25"))
            self.checkbox.select()
        else:
            self.configure(fg_color=("gray85", "gray17"))
            self.checkbox.deselect()

class GalleryView(ctk.CTkScrollableFrame):
    def __init__(self, master, client, on_item_click, on_selection_change=None, **kwargs):
        super().__init__(master, corner_radius=0, **kwargs)
        self.client = client
        self.on_item_click = on_item_click
        self.on_selection_change = on_selection_change
        self.items = []
        self.item_widgets = {}
        self.selected_ids = set()
        
        # Grid layout for items
        self.cols = 4
        for i in range(self.cols):
            self.grid_columnconfigure(i, weight=1)

    def set_items(self, items):
        # Clear existing
        for widget in self.item_widgets.values():
            widget.destroy()
        self.item_widgets.clear()
        self.items = items
        self.selected_ids.clear()
        self.current_page = 0
        self.items_per_page = 40
        self._render_page()

    def _render_page(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = self.items[start_idx:end_idx]
        
        for i, item in enumerate(page_items):
            idx = start_idx + i
            row = idx // self.cols
            col = idx % self.cols
            
            widget = GalleryItem(self, item, self._handle_item_click, self.client)
            widget.grid(row=row, column=col, padx=10, pady=10, sticky="n")
            self.item_widgets[item["id"]] = widget
            
        if end_idx < len(self.items):
            self.current_page += 1
            self.after(500, self._render_page)

    def _handle_item_click(self, screenshot_data, is_checkbox=False, is_selected=False):
        sid = screenshot_data["id"]
        
        if is_checkbox:
            if is_selected:
                self.selected_ids.add(sid)
                self.item_widgets[sid].set_selected(True)
            else:
                self.selected_ids.discard(sid)
                self.item_widgets[sid].set_selected(False)
                
            # If we select/deselect a checkbox, we also want to update app level multi-select state
            if self.on_selection_change:
                self.on_selection_change(list(self.selected_ids))
        else:
            # Deselect all others
            for widget in self.item_widgets.values():
                widget.set_selected(False)
            self.selected_ids.clear()
            
            self.selected_ids.add(sid)
            self.item_widgets[sid].set_selected(True)
            
            if self.on_selection_change:
                self.on_selection_change(list(self.selected_ids))
            
            if self.on_item_click:
                self.on_item_click(screenshot_data)
