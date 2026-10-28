"""
X-Plane MFD (Multi-Function Display) - Real-time aircraft data visualization

Requirements:
- Python 3.7+
- requests library (install with: pip install requests)
- pygame library (install with: pip install pygame)
- X-Plane 12.1.1+ running with Web API enabled

To run:
    source my_env/bin/activate  # activate venv
    python3 aircraft_mfd.py
Or simply:
    ./run_mfd.sh

USB Device Support:
    Supports ThrustMaster F16 MFD 2 (VID: 0x044f, PID: 0xb352)
    - Automatically detected when connected
    - Falls back to keyboard input if not connected
    - Buttons 0-9 on device map to panel selection

Keyboard Shortcuts (fallback when USB device not connected):
    0 - Show all panels (default view)
    1 - Show POSITION panel only (full screen)
    2 - Show WIND panel only (full screen)
    3 - Show ENVELOPE panel only (full screen)
    4 - Show NAVIGATION panel only (full screen)
    5 - Show FLIGHT DATA panel only (full screen)
    6 - Show ENGINE panel only (full screen)
    7 - Show TURN PERF panel only (full screen)
    8 - Show VNAV panel only (full screen)
    9 - Show DENSITY ALT panel only (full screen)
"""

import tkinter as tk
from tkinter import font as tkfont
import requests
import json
from typing import Dict, Optional, Any
import time
import os
from pathlib import Path
import subprocess
import ctypes
import ctypes.util

try:
    import pygame.joystick
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("Warning: pygame not available. Install with: pip install pygame")


class XPlaneAPI:
    """Interface to X-Plane Web API"""
    
    def __init__(self, base_url: str = "http://localhost:8086/api/v2"):
        self.base_url = base_url
        self.dataref_cache: Dict[str, int] = {}
        
    def get_dataref_id_by_name(self, name: str) -> Optional[int]:
        """Get dataref ID by name, with caching"""
        if name in self.dataref_cache:
            return self.dataref_cache[name]
        
        try:
            response = requests.get(
                f"{self.base_url}/datarefs",
                headers={"Accept": "application/json"},
                params={"filter[name]": name},
                timeout=1
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    dataref_id = data["data"][0]["id"]
                    self.dataref_cache[name] = dataref_id
                    return dataref_id
        except Exception as e:
            print(f"Error getting dataref {name}: {e}")
        return None
    
    def get_dataref_value(self, name: str, index: Optional[int] = None) -> Optional[Any]:
        """Get current value of a dataref by name"""
        dataref_id = self.get_dataref_id_by_name(name)
        if dataref_id is None:
            return None
        
        try:
            params = {"index": index} if index is not None else {}
            response = requests.get(
                f"{self.base_url}/datarefs/{dataref_id}/value",
                headers={"Accept": "application/json"},
                params=params,
                timeout=1
            )
            if response.status_code == 200:
                data = response.json()
                value = data.get("data")
                
                # If requesting array element, X-Plane returns [value], extract it
                if index is not None and isinstance(value, list) and len(value) > 0:
                    return value[0]
                
                return value
        except Exception as e:
            print(f"Error getting value for {name}: {e}")
        return None


class USBDeviceManager:
    """Manager for F16 MFD 2 USB device input using SDL2 joystick API"""
    
    # F16 MFD 2 device identifiers (hardcoded as requested)
    TARGET_NAME = "Thrustmaster F16 MFD 2"  # Exact device name
    
    def __init__(self, button_callback):
        """Initialize USB device manager
        
        Args:
            button_callback: Function to call when a button is pressed, receives button_number (0-9)
        """
        self.button_callback = button_callback
        self.joystick = None
        self.device_connected = False
        self.last_button_states = [False] * 28  # F16 MFD 2 has 28 buttons
        self.sdl = None
        
        if not PYGAME_AVAILABLE:
            print("pygame not available - using keyboard fallback only")
            return
        
        # Load SDL2 library to call SDL_JoystickUpdate directly
        # Use pygame's bundled SDL2 to match the joystick instance
        try:
            import pygame
            # Try .dylibs subfolder first (pygame 2.x)
            sdl_path = os.path.join(os.path.dirname(pygame.__file__), '.dylibs', 'libSDL2-2.0.0.dylib')
            if os.path.exists(sdl_path):
                self.sdl = ctypes.CDLL(sdl_path)
                print(f"  - Loaded SDL2 from pygame: {sdl_path}")
            else:
                # Fallback to root pygame folder
                sdl_path = os.path.join(os.path.dirname(pygame.__file__), 'libSDL2-2.0.0.dylib')
                if os.path.exists(sdl_path):
                    self.sdl = ctypes.CDLL(sdl_path)
                    print(f"  - Loaded SDL2 from pygame: {sdl_path}")
        except Exception as e:
            print(f"  - Could not load SDL2: {e}")
        
        # Try to connect to the device
        self.detect_device()
    
    def detect_device(self):
        """Detect and initialize the F16 MFD 2 device"""
        try:
            # Initialize only joystick subsystem
            pygame.joystick.init()
            
            joystick_count = pygame.joystick.get_count()
            
            for i in range(joystick_count):
                joy = pygame.joystick.Joystick(i)
                device_name = joy.get_name()
                
                # Match exact device name (hardcoded as requested)
                if device_name == self.TARGET_NAME:
                    joy.init()
                    self.joystick = joy
                    self.device_connected = True
                    print(f"✓ F16 MFD 2 detected: {device_name}")
                    print(f"  - Buttons: {joy.get_numbuttons()}")
                    print(f"  - Using SDL2 joystick API")
                    
                    # Initialize button states
                    for btn in range(joy.get_numbuttons()):
                        self.last_button_states[btn] = False
                    
                    return True
            
            print("F16 MFD 2 not detected - using keyboard fallback")
            return False
            
        except Exception as e:
            print(f"Error detecting USB device: {e}")
            return False
    
    def poll_buttons_once(self):
        """Poll for button presses once (called from main thread)
        
        Returns True if device is still connected, False otherwise
        """
        if not self.device_connected or not self.joystick:
            return False
        
        try:
            # Call SDL_JoystickUpdate directly to update joystick state
            # This avoids pygame's event system which conflicts with tkinter
            if self.sdl:
                try:
                    self.sdl.SDL_JoystickUpdate()
                except Exception as e:
                    pass  # Silently ignore SDL_JoystickUpdate errors
            
            # Read button states directly
            for btn_idx in range(self.joystick.get_numbuttons()):
                button_pressed = self.joystick.get_button(btn_idx)
                
                # Detect button press (transition from not pressed to pressed)
                if button_pressed and not self.last_button_states[btn_idx]:
                    # Map button index to panel number (0-9)
                    if btn_idx <= 9:
                        print(f"✓ F16 MFD button {btn_idx} pressed → switching to panel {btn_idx}")
                        self.button_callback(btn_idx)
                    else:
                        # Button > 9, just show it was pressed for debugging
                        print(f"  (F16 MFD button {btn_idx} pressed - not mapped)")
                
                self.last_button_states[btn_idx] = button_pressed
            
            return True
            
        except Exception as e:
            print(f"Error polling USB device: {e}")
            import traceback
            traceback.print_exc()
            self.device_connected = False
            return False
    
    def is_connected(self):
        """Check if the F16 MFD 2 is connected"""
        return self.device_connected
    
    def cleanup(self):
        """Clean up resources"""
        if self.joystick:
            try:
                self.joystick.quit()
            except:
                pass
        try:
            pygame.joystick.quit()
        except:
            pass


class AircraftMFD:
    """Multi-Function Display for X-Plane aircraft data"""
    
    # MFD Color scheme (military green phosphor display)
    BG_COLOR = "#000000"
    PRIMARY_COLOR = "#00FF00"
    SECONDARY_COLOR = "#00AA00"
    DIM_COLOR = "#004400"
    ALERT_COLOR = "#FFAA00"
    WARNING_COLOR = "#FF0000"
    
    def __init__(self, root):
        self.root = root
        self.root.title("X-PLANE MFD")
        self.root.geometry("900x900")  # Wider for 3-column layout
        self.root.configure(bg=self.BG_COLOR)
        self.root.resizable(False, False)
        
        self.api = XPlaneAPI()
        self.is_connected = False
        self.fields_created = False  # Track if data fields have been created
        
        # Display mode: 0 = all panels, 1-9 = individual panel full screen
        self.display_mode = 0
        self.panel_map = {
            1: "POSITION",
            2: "WIND", 
            3: "ENVELOPE",
            4: "NAVIGATION",
            5: "FLIGHT DATA",
            6: "ENGINE",
            7: "TURN PERF",
            8: "VNAV",
            9: "DENSITY ALT"
        }
        
        # Error handling
        self.has_cpp_error = False
        self.cpp_error_message = ""
        
        # Initialize USB device manager for F16 MFD 2
        self.usb_device = USBDeviceManager(self.on_usb_button_press)
        
        # Load B612 Mono font
        self.load_custom_fonts()
        
        # Setup fonts - regular size for all-panels view
        self.title_font = tkfont.Font(family=self.font_family, size=14, weight="bold")
        self.data_font = tkfont.Font(family=self.font_family, size=12, weight="bold")
        self.label_font = tkfont.Font(family=self.font_family, size=10)
        self.small_font = tkfont.Font(family=self.font_family, size=8)
        
        # Large fonts for single-panel view
        self.title_font_large = tkfont.Font(family=self.font_family, size=32, weight="bold")
        self.data_font_large = tkfont.Font(family=self.font_family, size=28, weight="bold")
        self.label_font_large = tkfont.Font(family=self.font_family, size=22)
        self.small_font_large = tkfont.Font(family=self.font_family, size=16)
        
        # Track all labels for font updates
        self.header_labels = []
        self.data_value_labels = []
        self.data_label_labels = []
        
        # Initialize data variables
        self.init_data_variables()
        
        self.setup_ui()
        self.setup_keyboard_bindings()
        
        # Bind cleanup on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start main update loop (includes USB polling)
        self.update_display()
    
    def load_custom_fonts(self):
        """Load B612 Mono font (Airbus cockpit font)"""
        try:
            # Check if B612 Mono is available in system fonts
            available_fonts = list(tkfont.families())
            
            # Try different possible font names
            possible_names = ["B612 Mono", "B612Mono", "B612 Mono Regular"]
            
            for name in possible_names:
                if name in available_fonts:
                    self.font_family = name
                    print(f"Using {name} font")
                    return True
            
            # Fall back to Courier if B612 Mono not found
            print("B612 Mono not found, using Courier as fallback")
            self.font_family = "Courier"
            return False
            
        except Exception as e:
            print(f"Error loading fonts: {e}")
            self.font_family = "Courier"
            return False
    
    def init_data_variables(self):
        """Initialize all StringVar variables for data display"""
        # Position data
        self.lat_var = tk.StringVar(value="---")
        self.lon_var = tk.StringVar(value="---")
        self.alt_var = tk.StringVar(value="---")
        self.agl_var = tk.StringVar(value="---")
        
        # Navigation data
        self.heading_var = tk.StringVar(value="---")
        self.track_var = tk.StringVar(value="---")
        self.pitch_var = tk.StringVar(value="---")
        self.roll_var = tk.StringVar(value="---")
        
        # Flight data
        self.ias_var = tk.StringVar(value="---")
        self.gs_var = tk.StringVar(value="---")
        self.vs_var = tk.StringVar(value="---")
        self.mach_var = tk.StringVar(value="---")
        
        # Engine data
        self.n1_var = tk.StringVar(value="---")
        self.n2_var = tk.StringVar(value="---")
        self.throttle_var = tk.StringVar(value="---")
        self.fuel_var = tk.StringVar(value="---")
        
        # Wind data (calculated by C++ backend)
        self.headwind_var = tk.StringVar(value="---")
        self.crosswind_var = tk.StringVar(value="---")
        self.wind_spd_var = tk.StringVar(value="---")
        self.wind_dir_var = tk.StringVar(value="---")
        
        # Envelope margins
        self.stall_margin_var = tk.StringVar(value="---")
        self.speed_margin_var = tk.StringVar(value="---")
        self.load_factor_var = tk.StringVar(value="---")
        self.corner_spd_var = tk.StringVar(value="---")
        
        # Energy management
        self.spec_energy_var = tk.StringVar(value="---")
        self.energy_rate_var = tk.StringVar(value="---")
        
        # Turn performance
        self.turn_radius_var = tk.StringVar(value="---")
        self.turn_rate_var = tk.StringVar(value="---")
        self.turn_time_var = tk.StringVar(value="---")
        self.std_rate_bank_var = tk.StringVar(value="---")
        
        # VNAV data
        self.tod_dist_var = tk.StringVar(value="---")
        self.req_vs_var = tk.StringVar(value="---")
        self.fpa_var = tk.StringVar(value="---")
        self.vs_3deg_var = tk.StringVar(value="---")
        
        # Density altitude
        self.density_alt_var = tk.StringVar(value="---")
        self.perf_loss_var = tk.StringVar(value="---")
        self.isa_dev_var = tk.StringVar(value="---")
        self.eas_var = tk.StringVar(value="---")
    
    def setup_ui(self):
        """Setup the MFD user interface"""
        
        # Top header bar
        header = tk.Frame(self.root, bg=self.DIM_COLOR, height=40)
        header.pack(fill=tk.X, padx=2, pady=2)
        header.pack_propagate(False)
        
        tk.Label(
            header, 
            text="Aircraft Status", 
            font=self.title_font,
            bg=self.DIM_COLOR, 
            fg=self.PRIMARY_COLOR
        ).pack(pady=8)
        
        # Main display area
        self.main_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left column - Position & Navigation
        self.left_frame = tk.Frame(self.main_frame, bg=self.BG_COLOR)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=3)
        
        self.position_section, self.position_frame = self.create_section(self.left_frame, "POSITION")
        self.wind_section, self.wind_frame = self.create_section(self.left_frame, "WIND")
        self.envelope_section, self.envelope_frame = self.create_section(self.left_frame, "ENVELOPE")
        
        # Middle column - Flight Data & Engine
        self.middle_frame = tk.Frame(self.main_frame, bg=self.BG_COLOR)
        self.middle_frame.grid(row=0, column=1, sticky="nsew", padx=3)
        
        self.nav_section, self.nav_frame = self.create_section(self.middle_frame, "NAVIGATION")
        self.flight_section, self.flight_frame = self.create_section(self.middle_frame, "FLIGHT DATA")
        self.engine_section, self.engine_frame = self.create_section(self.middle_frame, "ENGINE")
        
        # Right column - Performance calculations
        self.right_frame = tk.Frame(self.main_frame, bg=self.BG_COLOR)
        self.right_frame.grid(row=0, column=2, sticky="nsew", padx=3)
        
        self.turn_section, self.turn_frame = self.create_section(self.right_frame, "TURN PERF")
        self.vnav_section, self.vnav_frame = self.create_section(self.right_frame, "VNAV")
        self.density_section, self.density_frame = self.create_section(self.right_frame, "DENSITY ALT")
        
        # Map sections for easy access by panel number
        self.sections = {
            1: self.position_section,
            2: self.wind_section,
            3: self.envelope_section,
            4: self.nav_section,
            5: self.flight_section,
            6: self.engine_section,
            7: self.turn_section,
            8: self.vnav_section,
            9: self.density_section
        }
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(2, weight=1)
        
        # Create data field rows (only once!)
        self.create_data_fields()
        
        # Error overlay (hidden by default)
        self.create_error_overlay()
        
        # Bottom status bar
        self.status_bar = tk.Frame(self.root, bg=self.DIM_COLOR, height=30)
        self.status_bar.pack(fill=tk.X, padx=2, pady=2, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)
        
        self.status_label = tk.Label(
            self.status_bar,
            text="● CONNECTING...",
            font=self.small_font,
            bg=self.DIM_COLOR,
            fg=self.ALERT_COLOR
        )
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Keyboard hint - update based on USB device status
        input_method = "F16 MFD" if self.usb_device.is_connected() else "KEYBOARD"
        self.keyboard_hint = tk.Label(
            self.status_bar,
            text=f"INPUT: {input_method} | [0-9] Switch Panel | [0] All Panels",
            font=self.small_font,
            bg=self.DIM_COLOR,
            fg=self.SECONDARY_COLOR
        )
        self.keyboard_hint.pack(side=tk.LEFT, padx=20, pady=5)
        
        self.time_label = tk.Label(
            self.status_bar,
            text="",
            font=self.small_font,
            bg=self.DIM_COLOR,
            fg=self.SECONDARY_COLOR
        )
        self.time_label.pack(side=tk.RIGHT, padx=10, pady=5)
    
    def create_error_overlay(self):
        """Create error overlay with big red X (hidden by default)"""
        self.error_overlay = tk.Frame(
            self.root, 
            bg="#000000",
            bd=0
        )
        
        # Canvas for drawing the red X
        self.error_canvas = tk.Canvas(
            self.error_overlay,
            bg="#000000",
            highlightthickness=0,
            width=600,
            height=400
        )
        self.error_canvas.pack(expand=True, fill=tk.BOTH)
        
        # Draw big red X (scaled for smaller canvas)
        x_color = self.WARNING_COLOR
        line_width = 15
        
        # Diagonal lines forming X (centered)
        self.error_canvas.create_line(225, 80, 525, 320, fill=x_color, width=line_width)
        self.error_canvas.create_line(525, 80, 225, 320, fill=x_color, width=line_width)
        
        # Error message
        self.error_text = tk.Label(
            self.error_overlay,
            text="",
            font=tkfont.Font(family=self.font_family, size=14, weight="bold"),
            bg="#000000",
            fg=self.WARNING_COLOR,
            wraplength=550,
            justify=tk.CENTER
        )
        self.error_text.pack(pady=15)
        
        # Instructions
        self.error_instruction = tk.Label(
            self.error_overlay,
            text="Press [0] to return to normal view",
            font=self.label_font,
            bg="#000000",
            fg=self.ALERT_COLOR
        )
        self.error_instruction.pack(pady=8)
        
        # Hide by default
        self.error_overlay.place_forget()
    
    def show_error_overlay(self, error_message: str):
        """Show error overlay with message"""
        self.has_cpp_error = True
        self.cpp_error_message = error_message
        self.error_text.config(text=f"C++ CALCULATION ERROR:\n\n{error_message}")
        
        # Place overlay on top of everything
        self.error_overlay.place(x=0, y=40, relwidth=1, relheight=1)
        self.error_overlay.lift()
    
    def hide_error_overlay(self):
        """Hide error overlay"""
        self.has_cpp_error = False
        self.cpp_error_message = ""
        self.error_overlay.place_forget()
    
    def create_section(self, parent, title: str) -> tuple:
        """Create a labeled section frame - returns (section_frame, content_frame)"""
        section = tk.Frame(parent, bg=self.BG_COLOR, relief=tk.RIDGE, bd=2, highlightbackground=self.DIM_COLOR)
        section.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Section header
        header = tk.Label(
            section,
            text=f"▬▬ {title} ▬▬",
            font=self.label_font,
            bg=self.BG_COLOR,
            fg=self.SECONDARY_COLOR
        )
        header.pack(pady=5)
        
        # Store reference for font updates
        self.header_labels.append(header)
        
        # Content frame
        content = tk.Frame(section, bg=self.BG_COLOR)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        return section, content
    
    def add_data_row(self, parent, label: str, value_var: tk.StringVar) -> None:
        """Add a data row to a section"""
        row = tk.Frame(parent, bg=self.BG_COLOR)
        row.pack(fill=tk.X, pady=2)
        
        label_widget = tk.Label(
            row,
            text=label,
            font=self.label_font,
            bg=self.BG_COLOR,
            fg=self.DIM_COLOR,
            width=12,
            anchor=tk.W
        )
        label_widget.pack(side=tk.LEFT)
        
        value_widget = tk.Label(
            row,
            textvariable=value_var,
            font=self.data_font,
            bg=self.BG_COLOR,
            fg=self.PRIMARY_COLOR,
            anchor=tk.E
        )
        value_widget.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Store references for font updates
        self.data_label_labels.append(label_widget)
        self.data_value_labels.append(value_widget)
    
    def setup_keyboard_bindings(self):
        """Setup keyboard shortcuts for display mode switching"""
        # Bind number keys 0-9
        for i in range(10):
            self.root.bind(str(i), lambda event, num=i: self.switch_display_mode(num))
    
    def on_usb_button_press(self, button_number: int):
        """Callback for USB device button presses
        
        Args:
            button_number: Button index from USB device (0-9)
        """
        # We're already on the main thread (called from update_display),
        # so we can update the display directly without queuing
        self.switch_display_mode(button_number)
        
        # Force immediate UI update to eliminate any delay
        self.root.update_idletasks()
    
    def on_closing(self):
        """Handle window close event"""
        print("Shutting down...")
        if hasattr(self, 'usb_device'):
            self.usb_device.cleanup()
        self.root.destroy()
    
    def update_font_sizes(self, use_large_fonts: bool):
        """Update all label fonts based on display mode"""
        if use_large_fonts:
            # Use large fonts for single-panel view
            label_font = self.label_font_large
            data_font = self.data_font_large
        else:
            # Use regular fonts for all-panels view
            label_font = self.label_font
            data_font = self.data_font
        
        # Update all header labels (section titles)
        for header in self.header_labels:
            header.config(font=label_font)
        
        # Update all data label labels (field names like "LATITUDE:")
        for label in self.data_label_labels:
            label.config(font=label_font)
        
        # Update all data value labels (actual values)
        for value_label in self.data_value_labels:
            value_label.config(font=data_font)
    
    def switch_display_mode(self, mode: int):
        """Switch between multi-panel and single-panel views"""
        if mode < 0 or mode > 9:
            return
        
        # Clear error overlay when switching away from mode 9
        if self.display_mode == 9 and mode != 9:
            self.hide_error_overlay()
        
        self.display_mode = mode
        
        if mode == 0:
            # Show all panels in 3-column layout
            self.show_all_panels()
            # Use regular font sizes
            self.update_font_sizes(use_large_fonts=False)
        else:
            # Show single panel in full screen
            self.show_single_panel(mode)
            # Use large font sizes
            self.update_font_sizes(use_large_fonts=True)
        
        # Update status bar to show current mode
        input_method = "F16 MFD" if self.usb_device.is_connected() else "KEYBOARD"
        if mode == 0:
            self.root.title("X-PLANE MFD - ALL PANELS")
            self.keyboard_hint.config(text=f"INPUT: {input_method} | [0-9] Switch Panel | [0] All Panels")
        else:
            panel_name = self.panel_map.get(mode, "UNKNOWN")
            self.root.title(f"X-PLANE MFD - {panel_name}")
            self.keyboard_hint.config(text=f"INPUT: {input_method} | [{mode}] {panel_name} | [0] Return to All")
    
    def show_all_panels(self):
        """Show all panels in 3-column layout"""
        # Restore original grid configuration for all column frames
        # Important: reset columnspan to 1 (default) to restore 3-column layout
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=3, columnspan=1)
        self.middle_frame.grid(row=0, column=1, sticky="nsew", padx=3, columnspan=1)
        self.right_frame.grid(row=0, column=2, sticky="nsew", padx=3, columnspan=1)
        
        # Make all sections visible in their original containers
        for section in self.sections.values():
            section.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def show_single_panel(self, panel_num: int):
        """Show single panel in full screen"""
        # Hide all column frames first
        self.left_frame.grid_remove()
        self.middle_frame.grid_remove()
        self.right_frame.grid_remove()
        
        # Get the selected section
        selected_section = self.sections.get(panel_num)
        if not selected_section:
            return
        
        # Determine which column frame contains this section
        if panel_num in [1, 2, 3]:
            # Position, Wind, Envelope - left column
            self.left_frame.grid(row=0, column=0, sticky="nsew", padx=3, columnspan=3)
            # Hide other sections in left column
            for i in [1, 2, 3]:
                if i == panel_num:
                    self.sections[i].pack(fill=tk.BOTH, expand=True, pady=5)
                else:
                    self.sections[i].pack_forget()
        elif panel_num in [4, 5, 6]:
            # Navigation, Flight Data, Engine - middle column
            self.middle_frame.grid(row=0, column=0, sticky="nsew", padx=3, columnspan=3)
            # Hide other sections in middle column
            for i in [4, 5, 6]:
                if i == panel_num:
                    self.sections[i].pack(fill=tk.BOTH, expand=True, pady=5)
                else:
                    self.sections[i].pack_forget()
        elif panel_num in [7, 8, 9]:
            # Turn Perf, VNAV, Density Alt - right column
            self.right_frame.grid(row=0, column=0, sticky="nsew", padx=3, columnspan=3)
            # Hide other sections in right column
            for i in [7, 8, 9]:
                if i == panel_num:
                    self.sections[i].pack(fill=tk.BOTH, expand=True, pady=5)
                else:
                    self.sections[i].pack_forget()
    
    def format_lat_lon(self, degrees: float, is_latitude: bool) -> str:
        """Format latitude/longitude for display"""
        if degrees is None:
            return "---"
        
        direction = ""
        if is_latitude:
            direction = "N" if degrees >= 0 else "S"
        else:
            direction = "E" if degrees >= 0 else "W"
        
        degrees = abs(degrees)
        deg = int(degrees)
        minutes = (degrees - deg) * 60
        
        return f"{deg:03d}°{minutes:06.3f}'{direction}"
    
    def calculate_flight_data(self, tas, gs, heading, track, ias, mach, altitude, agl, vs, 
                              weight, bank, vso, vne, mmo) -> Optional[dict]:
        """Call C++ flight calculator for comprehensive calculations"""
        try:
            script_dir = Path(__file__).parent
            calculator_path = script_dir / "flight_calculator"
            
            if not calculator_path.exists():
                return None
            
            # Call the C++ program with all parameters
            result = subprocess.run(
                [str(calculator_path),
                 str(tas), str(gs), str(heading), str(track),
                 str(ias), str(mach), str(altitude), str(agl), str(vs),
                 str(weight), str(bank), str(vso), str(vne), str(mmo)],
                capture_output=True,
                text=True,
                timeout=0.1  # 100ms timeout
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                return None
                
        except Exception as e:
            # Silently fail - don't spam console
            return None
    
    def calculate_turn_performance(self, tas_kts, bank_deg) -> Optional[dict]:
        """Call C++ turn calculator"""
        try:
            script_dir = Path(__file__).parent
            calculator_path = script_dir / "turn_calculator"
            
            if not calculator_path.exists():
                return None
            
            # Calculate for a 90-degree turn (common reference)
            result = subprocess.run(
                [str(calculator_path), str(tas_kts), str(bank_deg), "90"],
                capture_output=True,
                text=True,
                timeout=0.1
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except:
            return None
    
    def calculate_vnav_data(self, current_alt_ft, gs_kts, vs_fpm) -> Optional[dict]:
        """Call C++ VNAV calculator - assumes descent to 10000 ft at 100nm"""
        try:
            script_dir = Path(__file__).parent
            calculator_path = script_dir / "vnav_calculator"
            
            if not calculator_path.exists():
                return None
            
            # Simplified: show TOD for descent to 10000 ft
            target_alt = 10000.0
            distance_nm = 100.0  # Reference distance
            
            result = subprocess.run(
                [str(calculator_path), 
                 str(current_alt_ft), str(target_alt), str(distance_nm), 
                 str(gs_kts), str(vs_fpm)],
                capture_output=True,
                text=True,
                timeout=0.1
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except:
            return None
    
    def calculate_density_altitude(self, pressure_alt_ft, oat_celsius, ias_kts, tas_kts) -> Optional[dict]:
        """Call C++ density altitude calculator
        
        When display_mode == 9 (viewing DENSITY ALT panel in full screen),
        this will force the C++ code to throw an exception, demonstrating
        error handling. A big red X will appear on screen.
        """
        try:
            script_dir = Path(__file__).parent
            calculator_path = script_dir / "density_altitude_calculator"
            
            if not calculator_path.exists():
                return None
            
            # Force exception when viewing density alt panel in full screen (mode 9)
            # This demonstrates C++ exception handling and error display
            force_exception = "1" if self.display_mode == 9 else "0"
            
            result = subprocess.run(
                [str(calculator_path), 
                 str(pressure_alt_ft), str(oat_celsius), str(ias_kts), str(tas_kts),
                 force_exception],
                capture_output=True,
                text=True,
                timeout=0.1
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                # Check if this is an actual exception (return code 1) vs graceful error handling (return code 3)
                # Return code 1 = uncaught exception (non-compliant version)
                # Return code 3 = gracefully handled error (compliant version)
                if self.display_mode == 9 and result.returncode == 1 and not self.has_cpp_error:
                    # Only show big X for actual exceptions (non-compliant behavior)
                    # Extract error message from stderr
                    error_lines = result.stderr.strip().split('\n')
                    # Get the actual error message (first line after "Error:")
                    error_msg = "Unknown C++ error"
                    for line in error_lines:
                        if line.startswith("Error:"):
                            error_msg = line.replace("Error:", "").strip()
                            break
                    
                    # Show error overlay for uncaught exceptions only
                    self.show_error_overlay(error_msg)
                
                return None
        except Exception as e:
            if self.display_mode == 9 and not self.has_cpp_error:
                self.show_error_overlay(f"Failed to execute calculator: {str(e)}")
            return None
    
    def update_display(self):
        """Main update loop for the MFD"""
        # Poll USB device buttons (if connected) - MUST be on main thread for macOS
        if self.usb_device.is_connected():
            self.usb_device.poll_buttons_once()
        
        try:
            # Test connection
            response = requests.get(f"{self.api.base_url}/datarefs/count", timeout=1)
            if response.status_code == 200:
                if not self.is_connected:
                    self.is_connected = True
                    self.status_label.config(text="● CONNECTED", fg=self.PRIMARY_COLOR)
                
                self.update_data()
            else:
                if self.is_connected:
                    self.is_connected = False
                    self.status_label.config(text="● CONNECTION LOST", fg=self.WARNING_COLOR)
        except Exception as e:
            if self.is_connected or not hasattr(self, '_first_error_shown'):
                print(f"Connection error: {e}")
                self._first_error_shown = True
            if self.is_connected:
                self.is_connected = False
            self.status_label.config(text="● DISCONNECTED", fg=self.WARNING_COLOR)
        
        # Update time display
        self.time_label.config(text=time.strftime("%H:%M:%S UTC", time.gmtime()))
        
        # Schedule next update (10 Hz)
        self.root.after(100, self.update_display)
    
    def create_data_fields(self):
        """Create all data field labels (called only once during UI setup)"""
        # Position data rows
        self.add_data_row(self.position_frame, "LATITUDE:", self.lat_var)
        self.add_data_row(self.position_frame, "LONGITUDE:", self.lon_var)
        self.add_data_row(self.position_frame, "ALTITUDE:", self.alt_var)
        self.add_data_row(self.position_frame, "AGL:", self.agl_var)
        
        # Navigation data rows
        self.add_data_row(self.nav_frame, "HEADING:", self.heading_var)
        self.add_data_row(self.nav_frame, "TRACK:", self.track_var)
        self.add_data_row(self.nav_frame, "PITCH:", self.pitch_var)
        self.add_data_row(self.nav_frame, "ROLL:", self.roll_var)
        
        # Wind data rows (calculated by C++)
        self.add_data_row(self.wind_frame, "HEADWIND:", self.headwind_var)
        self.add_data_row(self.wind_frame, "CROSSWIND:", self.crosswind_var)
        self.add_data_row(self.wind_frame, "WIND SPD:", self.wind_spd_var)
        self.add_data_row(self.wind_frame, "WIND DIR:", self.wind_dir_var)
        
        # Envelope margin rows
        self.add_data_row(self.envelope_frame, "STALL MRG:", self.stall_margin_var)
        self.add_data_row(self.envelope_frame, "SPD MRG:", self.speed_margin_var)
        self.add_data_row(self.envelope_frame, "LOAD G:", self.load_factor_var)
        self.add_data_row(self.envelope_frame, "CORNER V:", self.corner_spd_var)
        
        # Flight data rows  
        self.add_data_row(self.flight_frame, "IAS:", self.ias_var)
        self.add_data_row(self.flight_frame, "GND SPD:", self.gs_var)
        self.add_data_row(self.flight_frame, "VERT SPD:", self.vs_var)
        self.add_data_row(self.flight_frame, "ENERGY:", self.spec_energy_var)
        
        # Engine data rows
        self.add_data_row(self.engine_frame, "N1:", self.n1_var)
        self.add_data_row(self.engine_frame, "N2:", self.n2_var)
        self.add_data_row(self.engine_frame, "THROTTLE:", self.throttle_var)
        self.add_data_row(self.engine_frame, "FUEL:", self.fuel_var)
        
        # Turn performance rows
        self.add_data_row(self.turn_frame, "RADIUS:", self.turn_radius_var)
        self.add_data_row(self.turn_frame, "TURN RATE:", self.turn_rate_var)
        self.add_data_row(self.turn_frame, "TIME 90°:", self.turn_time_var)
        self.add_data_row(self.turn_frame, "STD BANK:", self.std_rate_bank_var)
        
        # VNAV rows
        self.add_data_row(self.vnav_frame, "TOD DIST:", self.tod_dist_var)
        self.add_data_row(self.vnav_frame, "REQ VS:", self.req_vs_var)
        self.add_data_row(self.vnav_frame, "FPA:", self.fpa_var)
        self.add_data_row(self.vnav_frame, "VS 3°:", self.vs_3deg_var)
        
        # Density altitude rows
        self.add_data_row(self.density_frame, "DENS ALT:", self.density_alt_var)
        self.add_data_row(self.density_frame, "PERF LOSS:", self.perf_loss_var)
        self.add_data_row(self.density_frame, "ISA DEV:", self.isa_dev_var)
        self.add_data_row(self.density_frame, "EAS:", self.eas_var)
    
    def update_data(self):
        """Update all data fields from X-Plane"""
        try:
            # Position
            lat = self.api.get_dataref_value("sim/flightmodel/position/latitude")
            lon = self.api.get_dataref_value("sim/flightmodel/position/longitude")
            alt = self.api.get_dataref_value("sim/flightmodel/position/elevation")
            agl = self.api.get_dataref_value("sim/flightmodel/position/y_agl")
            
            if lat is not None:
                self.lat_var.set(self.format_lat_lon(lat, True))
            if lon is not None:
                self.lon_var.set(self.format_lat_lon(lon, False))
            if alt is not None:
                self.alt_var.set(f"{alt * 3.28084:.0f} FT")
            if agl is not None:
                self.agl_var.set(f"{agl * 3.28084:.0f} FT")
            
            # Navigation
            heading = self.api.get_dataref_value("sim/flightmodel/position/psi")
            pitch = self.api.get_dataref_value("sim/flightmodel/position/theta")
            roll = self.api.get_dataref_value("sim/flightmodel/position/phi")
            track = self.api.get_dataref_value("sim/flightmodel/position/hpath")
            
            if heading is not None:
                self.heading_var.set(f"{heading:06.2f}°")
            if pitch is not None:
                self.pitch_var.set(f"{pitch:+06.2f}°")
            if roll is not None:
                self.roll_var.set(f"{roll:+06.2f}°")
            if track is not None:
                self.track_var.set(f"{track:06.2f}°")
            
            # Flight data
            # Use cockpit gauge IAS (what pilot sees) instead of raw indicated_airspeed
            # The raw dataref can be miscalibrated or in wrong units for some aircraft
            ias = self.api.get_dataref_value("sim/cockpit2/gauges/indicators/airspeed_kts_pilot")
            if ias is None:  # Fallback to raw if cockpit gauge not available
                ias = self.api.get_dataref_value("sim/flightmodel/position/indicated_airspeed")
            gs = self.api.get_dataref_value("sim/flightmodel/position/groundspeed")
            vs = self.api.get_dataref_value("sim/cockpit2/gauges/indicators/vvi_fpm_pilot")
            mach = self.api.get_dataref_value("sim/flightmodel/misc/machno")
            
            if ias is not None:
                self.ias_var.set(f"{ias:.1f} KTS")
            if gs is not None:
                # Convert m/s to knots
                self.gs_var.set(f"{gs * 1.94384:.1f} KTS")
            if vs is not None:
                self.vs_var.set(f"{vs:+.0f} FPM")
            if mach is not None:
                self.mach_var.set(f"M {mach:.3f}")
            
            # Engine data - try multiple sources for compatibility
            # Try N1/N2 first (jets)
            n1 = self.api.get_dataref_value("sim/cockpit2/engine/indicators/N1_percent", 0)
            n2 = self.api.get_dataref_value("sim/cockpit2/engine/indicators/N2_percent", 0)
            
            # If N1/N2 not available, try RPM (props)
            if n1 is None or n1 == 0:
                rpm = self.api.get_dataref_value("sim/cockpit2/engine/indicators/engine_speed_rpm", 0)
                if rpm is not None and rpm > 0:
                    self.n1_var.set(f"{rpm:.0f} RPM")
                else:
                    self.n1_var.set("---")
            else:
                self.n1_var.set(f"{n1:.1f}%")
            
            if n2 is not None and n2 > 0:
                self.n2_var.set(f"{n2:.1f}%")
            else:
                # Try prop RPM as alternative
                prop_rpm = self.api.get_dataref_value("sim/cockpit2/engine/indicators/prop_speed_rpm", 0)
                if prop_rpm is not None and prop_rpm > 0:
                    self.n2_var.set(f"{prop_rpm:.0f} RPM")
                else:
                    self.n2_var.set("---")
            
            throttle = self.api.get_dataref_value("sim/cockpit2/engine/actuators/throttle_ratio", 0)
            if throttle is not None:
                self.throttle_var.set(f"{throttle * 100:.1f}%")
            
            fuel_total = self.api.get_dataref_value("sim/flightmodel/weight/m_fuel_total")
            if fuel_total is not None:
                # Convert kg to lbs
                self.fuel_var.set(f"{fuel_total * 2.20462:.0f} LBS")
            
            # Get additional data for comprehensive calculations
            tas = self.api.get_dataref_value("sim/flightmodel/position/true_airspeed")
            weight = self.api.get_dataref_value("sim/flightmodel/weight/m_total")
            vso = self.api.get_dataref_value("sim/aircraft/view/acf_Vso")
            vne = self.api.get_dataref_value("sim/aircraft/view/acf_Vne")
            mmo_val = self.api.get_dataref_value("sim/aircraft/view/acf_Mmo")
            
            # Convert units for calculator
            gs_kts = gs * 1.94384 if gs is not None else 0
            alt_ft = alt * 3.28084 if alt is not None else 0
            agl_ft = agl * 3.28084 if agl is not None else 0
            
            # Call comprehensive C++ flight calculator
            if all(v is not None for v in [tas, gs, heading, track, ias, mach, alt, agl, vs, weight, roll, vso, vne, mmo_val]):
                flight_data = self.calculate_flight_data(
                    tas, gs_kts, heading, track, ias, mach, alt_ft, agl_ft, vs,
                    weight, roll, vso, vne, mmo_val
                )
                
                if flight_data:
                    # Extract and display wind data
                    wind = flight_data.get('wind', {})
                    hw = wind.get('headwind', 0)
                    cw = wind.get('crosswind', 0)
                    wind_spd = wind.get('speed_kts', 0)
                    wind_dir = wind.get('direction_from', 0)
                    
                    if hw >= 0:
                        self.headwind_var.set(f"{hw:.1f} KT")
                    else:
                        self.headwind_var.set(f"{abs(hw):.1f} TAIL")
                    
                    if abs(cw) < 0.5:
                        self.crosswind_var.set("CALM")
                    elif cw > 0:
                        self.crosswind_var.set(f"{cw:.1f} R")
                    else:
                        self.crosswind_var.set(f"{abs(cw):.1f} L")
                    
                    self.wind_spd_var.set(f"{wind_spd:.1f} KT")
                    self.wind_dir_var.set(f"{wind_dir:03.0f}°")
                    
                    # Extract and display envelope margins
                    envelope = flight_data.get('envelope', {})
                    stall_mrg = envelope.get('stall_margin_pct', 0)
                    speed_mrg = envelope.get('min_margin_pct', 0)
                    load_g = envelope.get('load_factor', 1.0)
                    corner = envelope.get('corner_speed_kts', 0)
                    
                    # Color code stall margin
                    if stall_mrg < 10:
                        stall_color = "CRIT"
                    elif stall_mrg < 20:
                        stall_color = "WARN"
                    else:
                        stall_color = ""
                    
                    self.stall_margin_var.set(f"{stall_mrg:.0f}% {stall_color}".strip())
                    self.speed_margin_var.set(f"{speed_mrg:.0f}%")
                    self.load_factor_var.set(f"{load_g:.2f} G")
                    self.corner_spd_var.set(f"{corner:.0f} KT")
                    
                    # Extract and display energy data
                    energy = flight_data.get('energy', {})
                    spec_energy = energy.get('specific_energy_ft', 0)
                    trend = energy.get('trend', 0)
                    
                    trend_arrow = "↑" if trend > 0 else "↓" if trend < 0 else "→"
                    self.spec_energy_var.set(f"{spec_energy:.0f} {trend_arrow}")
            
            # Call turn performance calculator
            if tas is not None and roll is not None:
                turn_data = self.calculate_turn_performance(tas, abs(roll))
                if turn_data:
                    radius_nm = turn_data.get('radius_nm', 0)
                    turn_rate = turn_data.get('turn_rate_dps', 0)
                    turn_time = turn_data.get('time_to_turn_sec', 0)
                    std_bank = turn_data.get('standard_rate_bank', 0)
                    
                    if radius_nm < 10:
                        self.turn_radius_var.set(f"{radius_nm:.2f} NM")
                    else:
                        self.turn_radius_var.set(f"{radius_nm:.1f} NM")
                    
                    self.turn_rate_var.set(f"{turn_rate:.1f} °/s")
                    self.turn_time_var.set(f"{turn_time:.0f} SEC")
                    self.std_rate_bank_var.set(f"{std_bank:.1f}°")
            
            # Call VNAV calculator
            if alt_ft is not None and gs_kts is not None and vs is not None:
                vnav_data = self.calculate_vnav_data(alt_ft, gs_kts, vs)
                if vnav_data:
                    tod_dist = vnav_data.get('tod_distance_nm', 0)
                    req_vs = vnav_data.get('required_vs_fpm', 0)
                    fpa = vnav_data.get('flight_path_angle_deg', 0)
                    vs_3deg = vnav_data.get('vs_for_3deg', 0)
                    
                    self.tod_dist_var.set(f"{tod_dist:.1f} NM")
                    self.req_vs_var.set(f"{req_vs:+.0f} FPM")
                    self.fpa_var.set(f"{fpa:+.1f}°")
                    self.vs_3deg_var.set(f"{vs_3deg:.0f} FPM")
            
            # Call density altitude calculator
            # Get OAT (outside air temperature)
            oat = self.api.get_dataref_value("sim/cockpit2/temperature/outside_air_temp_degc")
            if oat is not None and alt_ft is not None and ias is not None and tas is not None:
                da_data = self.calculate_density_altitude(alt_ft, oat, ias, tas)
                if da_data:
                    dens_alt = da_data.get('density_altitude_ft', 0)
                    perf_loss = da_data.get('performance_loss_pct', 0)
                    isa_dev = da_data.get('temperature_deviation_c', 0)
                    eas = da_data.get('eas_kts', 0)
                    
                    self.density_alt_var.set(f"{dens_alt:.0f} FT")
                    self.perf_loss_var.set(f"{perf_loss:.0f}%")
                    
                    # Color code ISA deviation
                    if abs(isa_dev) < 5:
                        self.isa_dev_var.set(f"{isa_dev:+.0f}°C")
                    else:
                        self.isa_dev_var.set(f"{isa_dev:+.0f}°C !")
                    
                    self.eas_var.set(f"{eas:.0f} KT")
        
        except Exception as e:
            print(f"Error updating data: {e}")


def main():
    """Main entry point"""
    root = tk.Tk()
    app = AircraftMFD(root)
    
    # Center window on screen
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()


if __name__ == "__main__":
    main()

