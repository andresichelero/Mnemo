import customtkinter as ctk

class TopBar(ctk.CTkFrame):
    def __init__(self, master, search_callback, open_settings_callback, **kwargs):
        super().__init__(master, height=50, corner_radius=0, **kwargs)
        self.search_callback = search_callback
        self.open_settings_callback = open_settings_callback
        self._search_job = None
        
        self.grid_columnconfigure(1, weight=1)
        
        self.title_label = ctk.CTkLabel(self, text="Mnemo", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        
        self.search_entry = ctk.CTkEntry(self, placeholder_text="Search semantic, text or tags...", width=400)
        self.search_entry.grid(row=0, column=1, padx=20, pady=10)
        self.search_entry.bind("<KeyRelease>", self._on_search_change)
        
        self.upload_btn = ctk.CTkButton(self, text="Upload", width=80, command=self._trigger_upload)
        self.upload_btn.grid(row=0, column=2, padx=(20, 10), pady=10, sticky="e")
        
        self.settings_btn = ctk.CTkButton(self, text="Settings", width=80, command=self.open_settings_callback)
        self.settings_btn.grid(row=0, column=3, padx=(10, 20), pady=10, sticky="e")
        
    def _trigger_upload(self):
        if hasattr(self.master, "manual_upload"):
            self.master.manual_upload()

    def _on_search_change(self, event):
        # Debounce de 400ms
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(400, self._trigger_search)
        
    def _trigger_search(self):
        query = self.search_entry.get()
        if self.search_callback:
            self.search_callback(query)
