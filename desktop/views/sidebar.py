import customtkinter as ctk

class Sidebar(ctk.CTkFrame):
    def __init__(self, master, client, filter_callback, **kwargs):
        super().__init__(master, width=200, corner_radius=0, **kwargs)
        self.client = client
        self.filter_callback = filter_callback
        
        self.pack_propagate(False)
        self.grid_propagate(False)
        
        self.title_label = ctk.CTkLabel(self, text="Folders", font=ctk.CTkFont(size=16, weight="bold"))
        self.title_label.pack(pady=10, padx=10, anchor="w")
        
        self.all_btn = ctk.CTkButton(self, text="All Screenshots", fg_color="transparent", 
                                     text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                     anchor="w", command=lambda: self._select_folder(None))
        self.all_btn.pack(fill="x", padx=10, pady=2)
        
        self.scrollable = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scrollable.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.create_btn = ctk.CTkButton(self, text="+ New Folder", command=self._create_folder)
        self.create_btn.pack(side="bottom", fill="x", padx=10, pady=10)
        
        self.folders = []
        self.folder_btns = []
        
    def load_folders(self):
        def fetch():
            res = self.client.get_folders()
            self.after(0, self._update_ui, res)
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def _update_ui(self, res):
        if "error" not in res and isinstance(res, list):
            self.folders = res
            
            for btn in self.folder_btns:
                btn.destroy()
            self.folder_btns.clear()
            
            for f in self.folders:
                btn = ctk.CTkButton(self.scrollable, text=f.get("name", "Unknown"), fg_color="transparent",
                                    text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                    anchor="w", command=lambda folder_id=f.get("id"): self._select_folder(folder_id))
                btn.pack(fill="x", pady=2)
                self.folder_btns.append(btn)
                
    def _select_folder(self, folder_id):
        if self.filter_callback:
            self.filter_callback({"folder_id": folder_id} if folder_id else None)
            
    def _create_folder(self):
        dialog = ctk.CTkInputDialog(text="Enter folder name:", title="New Folder")
        name = dialog.get_input()
        if name:
            def create():
                self.client._request("POST", "/folders", json={"name": name, "path": f"/{name}"})
                self.after(0, self.load_folders)
            import threading
            threading.Thread(target=create, daemon=True).start()
