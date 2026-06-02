import customtkinter as ctk

class StatusBar(ctk.CTkFrame):
    def __init__(self, master, client, **kwargs):
        super().__init__(master, height=30, corner_radius=0, **kwargs)
        self.client = client
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)
        
        self.status_label = ctk.CTkLabel(self, text="Ready")
        self.status_label.grid(row=0, column=0, padx=10, pady=2, sticky="w")
        
        self.queue_label = ctk.CTkLabel(self, text="Queue: 0")
        self.queue_label.grid(row=0, column=1, padx=10, pady=2, sticky="e")
        
        self.ollama_label = ctk.CTkLabel(self, text="Ollama: ?")
        self.ollama_label.grid(row=0, column=2, padx=10, pady=2, sticky="e")
        
        self.telnyx_label = ctk.CTkLabel(self, text="Telnyx: ?")
        self.telnyx_label.grid(row=0, column=3, padx=10, pady=2, sticky="e")
        
        self._poll_status()
        
    def _poll_status(self):
        try:
            # We fetch health first because it has ollama/telnyx status if implemented
            health = self.client.get_health()
            if "error" not in health:
                o_up = health.get("ollama_up", False)
                t_up = health.get("telnyx_up", False)
                self.ollama_label.configure(text=f"Ollama: {'UP' if o_up else 'DOWN'}", 
                                           text_color="green" if o_up else "red")
                self.telnyx_label.configure(text=f"Telnyx: {'UP' if t_up else 'DOWN'}",
                                           text_color="green" if t_up else "red")
                                           
            # Fetch processing status
            status = self.client.get_processing_status()
            if "error" not in status:
                queue_size = status.get("queue_size", 0)
                is_idle = status.get("is_idle", False)
                
                self.queue_label.configure(text=f"Queue: {queue_size}")
                
                if queue_size > 0:
                    self.status_label.configure(text="Processing...", text_color="orange")
                elif is_idle:
                    self.status_label.configure(text="System Idle", text_color="green")
                else:
                    self.status_label.configure(text="System Active", text_color="gray")
                    
        except Exception as e:
            self.status_label.configure(text="Disconnected", text_color="red")
            
        # Poll every 5 seconds
        self.after(5000, self._poll_status)
