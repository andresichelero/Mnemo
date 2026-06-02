import customtkinter as ctk

class SettingsPanel(ctk.CTkToplevel):
    def __init__(self, master, client, **kwargs):
        super().__init__(master, **kwargs)
        self.client = client
        self.title("Settings")
        self.geometry("500x420")
        
        # Make modal
        self.transient(master)
        self.after(100, self.grab_set)
        
        self.grid_columnconfigure(1, weight=1)
        
        # Watched Folders
        self.watched_label = ctk.CTkLabel(self, text="Watched Folders (JSON array):")
        self.watched_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.watched_entry = ctk.CTkEntry(self)
        self.watched_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Ollama Model
        self.ollama_label = ctk.CTkLabel(self, text="Ollama Model:")
        self.ollama_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.ollama_combobox = ctk.CTkComboBox(self, values=["gemma4:e4b", "gemma3:4b", "qwen2.5vl:7b", "gemma4:9b", "moondream2"])
        self.ollama_combobox.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        # Telnyx API Key
        self.telnyx_label = ctk.CTkLabel(self, text="Telnyx API Key:")
        self.telnyx_label.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.telnyx_entry = ctk.CTkEntry(self, show="*")
        self.telnyx_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        # Processing Mode
        self.mode_label = ctk.CTkLabel(self, text="Processing Mode:")
        self.mode_label.grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.mode_combobox = ctk.CTkComboBox(self, values=["idle", "manual", "always"])
        self.mode_combobox.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        
        # Idle CPU Threshold
        self.idle_label = ctk.CTkLabel(self, text="Idle CPU Threshold (%):")
        self.idle_label.grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.idle_entry = ctk.CTkEntry(self)
        self.idle_entry.grid(row=4, column=1, padx=10, pady=10, sticky="ew")
        
        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=5, column=0, columnspan=2, pady=20)
        
        self.test_btn = ctk.CTkButton(self.btn_frame, text="Test Connections", command=self._test_connections)
        self.test_btn.pack(side="left", padx=10)
        
        self.save_btn = ctk.CTkButton(self.btn_frame, text="Save Settings", command=self._save_settings)
        self.save_btn.pack(side="right", padx=10)
        
        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.grid(row=6, column=0, columnspan=2, pady=10)
        
        self._load_settings()
        
    def _load_settings(self):
        res = self.client.get_settings()
        if "error" not in res:
            # clear existing before inserting
            self.watched_entry.delete(0, 'end')
            self.telnyx_entry.delete(0, 'end')
            
            self.watched_entry.insert(0, res.get("watched_folders", "[]"))
            self.ollama_combobox.set(res.get("ollama_model", "gemma3:4b"))
            self.telnyx_entry.insert(0, res.get("telnyx_api_key", ""))
            self.mode_combobox.set(res.get("processing_mode", "idle"))
            self.idle_entry.insert(0, res.get("idle_threshold_cpu", "10"))
            
    def _save_settings(self):
        updates = {
            "watched_folders": self.watched_entry.get(),
            "ollama_model": self.ollama_combobox.get(),
            "telnyx_api_key": self.telnyx_entry.get(),
            "processing_mode": self.mode_combobox.get(),
            "idle_threshold_cpu": self.idle_entry.get()
        }
        res = self.client.update_settings(updates)
        if "error" not in res:
            self.status_label.configure(text="Settings saved!", text_color="green")
            self.after(2000, self.destroy)
        else:
            self.status_label.configure(text=f"Error: {res['error']}", text_color="red")
            
    def _test_connections(self):
        self.status_label.configure(text="Testing...", text_color="orange")
        self.update()
        res = self.client.validate_settings()
        if "error" not in res:
            o_ok = res.get("ollama", {}).get("connected", False)
            t_ok = res.get("telnyx", {}).get("connected", False)
            msg = f"Ollama: {'OK' if o_ok else 'FAIL'} | Telnyx: {'OK' if t_ok else 'FAIL'}"
            self.status_label.configure(text=msg, text_color="green" if o_ok and t_ok else "red")
        else:
            self.status_label.configure(text="Validation failed.", text_color="red")
