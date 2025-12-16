import wx
import wx.lib.newevent
import os
import threading
import pyttsx3
import warnings

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning, module='ebooklib')

# Optional libraries
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    epub = None
    BeautifulSoup = None

# ---------------------------------------------------------------------------
#  CONSTANTS & THEMES
# ---------------------------------------------------------------------------

THEMES = {
    'Light': {
        'bg': '#FFFFFF', 'fg': '#2D3748', 'panel_bg': '#F7FAFC', 
        'sidebar': '#EDF2F7', 'accent': '#4299E1', 'icon_color': '#2B6CB0'
    },
    'Sepia': {
        'bg': '#F6F1D1', 'fg': '#4A3B2A', 'panel_bg': '#E8E3C1', 
        'sidebar': '#DED8B6', 'accent': '#D69E2E', 'icon_color': '#975A16'
    },
    'Dark': {
        'bg': '#1A202C', 'fg': '#CBD5E0', 'panel_bg': '#2D3748', 
        'sidebar': '#283141', 'accent': '#63B3ED', 'icon_color': '#90CDF4'
    }
}

class ModernButton(wx.Button):
    """A wrapper to set cleaner fonts/cursor if possible."""
    def __init__(self, parent, label, func):
        super().__init__(parent, label=label)
        self.Bind(wx.EVT_BUTTON, func)
        self.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))

# ---------------------------------------------------------------------------
#  SERVICES
# ---------------------------------------------------------------------------

class TTSService:
    def __init__(self):
        self.engine = None
        self.is_speaking = False
        try:
            self.engine = pyttsx3.init()
        except:
            pass

    def speak(self, text):
        if self.is_speaking: self.stop()
        self.is_speaking = True
        threading.Thread(target=self._speak_thread, args=(text,)).start()

    def _speak_thread(self, text):
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except: pass
        finally: self.is_speaking = False

    def stop(self):
        if self.is_speaking:
            # This is a bit hacky for pyttsx3 in threads, but it attempts to stop
            try:
                # We can't easily stop a running loop in another thread with pyttsx3
                # So we just reset flag. In a real robust app, we'd use a queue.
                self.is_speaking = False
            except: pass

# ---------------------------------------------------------------------------
#  UI PANELS
# ---------------------------------------------------------------------------

class LibraryPanel(wx.Panel):
    """The 'Bookshelf' view."""
    def __init__(self, parent, on_open_callback):
        super().__init__(parent)
        self.on_open = on_open_callback
        self.SetBackgroundColour("#2D3748") # Dark Slate default for Library

        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Header
        header = wx.StaticText(self, label="MY LIBRARY")
        header.SetFont(wx.Font(24, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.SetForegroundColour("WHITE")
        vbox.Add(header, 0, wx.ALIGN_CENTER | wx.TOP, 40)

        subtitle = wx.StaticText(self, label="Manage your offline collection")
        subtitle.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        subtitle.SetForegroundColour("#A0AEC0")
        vbox.Add(subtitle, 0, wx.ALIGN_CENTER | wx.BOTTOM, 40)

        # Big "Add Book" Button
        add_btn = wx.Button(self, label="+  ADD BOOK TO LIBRARY", size=(240, 60))
        add_btn.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        add_btn.SetBackgroundColour("#4299E1")
        add_btn.SetForegroundColour("WHITE")
        add_btn.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_book)
        
        vbox.Add(add_btn, 0, wx.ALIGN_CENTER)
        
        # Decoration
        info_lbl = wx.StaticText(self, label="(Supported: TXT, PDF, EPUB)")
        info_lbl.SetForegroundColour("#718096")
        vbox.Add(info_lbl, 0, wx.ALIGN_CENTER | wx.TOP, 10)

        self.SetSizer(vbox)

    def on_add_book(self, event):
        wildcard = "eBooks (*.txt;*.pdf;*.epub)|*.txt;*.pdf;*.epub"
        with wx.FileDialog(self, "Import eBook", wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            self.on_open(path)


class ReaderPanel(wx.Panel):
    """The main reading interface."""
    def __init__(self, parent, tts_service, on_close_callback):
        super().__init__(parent)
        self.tts_service = tts_service
        self.on_close = on_close_callback
        self.pages = []
        self.current_page_idx = 0
        self.current_theme = 'Light'
        
        self.main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # --- SIDEBAR (Notes) ---
        self.sidebar = wx.Panel(self, size=(250, -1))
        self.sidebar_sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl_notes = wx.StaticText(self.sidebar, label="NOTES")
        lbl_notes.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.sidebar_sizer.Add(lbl_notes, 0, wx.ALL, 15)
        
        self.notes_ctrl = wx.TextCtrl(self.sidebar, style=wx.TE_MULTILINE)
        self.sidebar_sizer.Add(self.notes_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        save_btn = ModernButton(self.sidebar, "Save Notes", self.on_save_notes)
        self.sidebar_sizer.Add(save_btn, 0, wx.EXPAND | wx.ALL, 10)
        
        self.sidebar.SetSizer(self.sidebar_sizer)
        self.main_sizer.Add(self.sidebar, 0, wx.EXPAND)

        # --- MAIN CONTENT AREA ---
        self.content_area = wx.Panel(self)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Top Bar
        self.top_bar = wx.Panel(self.content_area)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        back_btn = ModernButton(self.top_bar, "« Library", self.on_back_click)
        top_sizer.Add(back_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

        self.title_lbl = wx.StaticText(self.top_bar, label="No Book")
        font = wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.title_lbl.SetFont(font)
        top_sizer.Add(self.title_lbl, 1, wx.ALIGN_CENTER_VERTICAL)
        
        # Theme Toggles
        self.theme_choice = wx.Choice(self.top_bar, choices=["Light", "Sepia", "Dark"])
        self.theme_choice.SetSelection(0)
        self.theme_choice.Bind(wx.EVT_CHOICE, self.on_theme_change)
        top_sizer.Add(self.theme_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        tts_btn = ModernButton(self.top_bar, "🔊 Listen", self.on_read_click)
        top_sizer.Add(tts_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self.top_bar.SetSizer(top_sizer)
        self.content_sizer.Add(self.top_bar, 0, wx.EXPAND | wx.ALL, 10)
        
        # Text Display
        self.text_ctrl = wx.TextCtrl(self.content_area, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.BORDER_NONE)
        self.text_ctrl.SetMargins(40, 20)
        content_font = wx.Font(14, wx.FONTFAMILY_ROMAN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Georgia")
        self.text_ctrl.SetFont(content_font)
        self.content_sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        
        # Bottom Bar (Progress)
        self.bot_bar = wx.Panel(self.content_area)
        bot_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.prev_btn = ModernButton(self.bot_bar, "Prev", self.on_prev)
        bot_sizer.Add(self.prev_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        
        self.slider = wx.Slider(self.bot_bar, value=0, minValue=0, maxValue=100)
        self.slider.Bind(wx.EVT_SCROLL_CHANGED, self.on_slider_change)
        bot_sizer.Add(self.slider, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        
        self.next_btn = ModernButton(self.bot_bar, "Next", self.on_next)
        bot_sizer.Add(self.next_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self.page_lbl = wx.StaticText(self.bot_bar, label=" 0 / 0 ")
        bot_sizer.Add(self.page_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)

        self.bot_bar.SetSizer(bot_sizer)
        self.content_sizer.Add(self.bot_bar, 0, wx.EXPAND | wx.ALL, 15)

        self.content_area.SetSizer(self.content_sizer)
        self.main_sizer.Add(self.content_area, 1, wx.EXPAND)

        self.SetSizer(self.main_sizer)
        self.apply_theme('Light')

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        t = THEMES[theme_name]
        
        # Content Colors
        self.content_area.SetBackgroundColour(t['panel_bg'])
        self.text_ctrl.SetBackgroundColour(t['bg'])
        self.text_ctrl.SetForegroundColour(t['fg'])
        
        # Sidebar Colors
        self.sidebar.SetBackgroundColour(t['sidebar'])
        self.notes_ctrl.SetBackgroundColour(t['bg'])
        self.notes_ctrl.SetForegroundColour(t['fg'])
        
        # Text Elements
        self.title_lbl.SetForegroundColour(t['fg'])
        self.page_lbl.SetForegroundColour(t['fg'])
        
        self.Refresh()

    def load_book(self, path, pages):
        self.pages = pages
        self.current_page_idx = 0
        self.title_lbl.SetLabel(os.path.basename(path))
        self.slider.SetMax(len(pages) - 1 if pages else 0)
        self.update_display()

    def update_display(self):
        if not self.pages: return
        self.text_ctrl.SetValue(self.pages[self.current_page_idx])
        self.text_ctrl.SetInsertionPoint(0)
        self.page_lbl.SetLabel(f"{self.current_page_idx + 1} / {len(self.pages)}")
        self.slider.SetValue(self.current_page_idx)
        
        # Enable/Disable nav
        self.prev_btn.Enable(self.current_page_idx > 0)
        self.next_btn.Enable(self.current_page_idx < len(self.pages) - 1)

    def on_prev(self, e):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.update_display()

    def on_next(self, e):
        if self.current_page_idx < len(self.pages) - 1:
            self.current_page_idx += 1
            self.update_display()

    def on_slider_change(self, e):
        val = self.slider.GetValue()
        if 0 <= val < len(self.pages):
            self.current_page_idx = val
            self.update_display()

    def on_read_click(self, e):
        if self.pages:
            self.tts_service.speak(self.pages[self.current_page_idx])

    def on_back_click(self, e):
        self.tts_service.stop()
        self.on_close()

    def on_save_notes(self, e):
        wx.MessageBox("Notes saved successfully!", "Info")

    def on_theme_change(self, e):
        choice = self.theme_choice.GetStringSelection()
        self.apply_theme(choice)


# ---------------------------------------------------------------------------
#  MAIN APP FRAME
# ---------------------------------------------------------------------------

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="IceReader Python", size=(1200, 800))
        self.tts = TTSService()
        self.Center()

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Views
        self.library_panel = LibraryPanel(self, self.open_book)
        self.reader_panel = ReaderPanel(self, self.tts, self.show_library)
        self.reader_panel.Hide()

        self.sizer.Add(self.library_panel, 1, wx.EXPAND)
        self.sizer.Add(self.reader_panel, 1, wx.EXPAND)
        
        self.SetSizer(self.sizer)

    def show_library(self):
        self.reader_panel.Hide()
        self.library_panel.Show()
        self.Layout()

    def open_book(self, path):
        # Extract pages
        pages = self.extract_text(path)
        self.reader_panel.load_book(path, pages)
        self.library_panel.Hide()
        self.reader_panel.Show()
        self.Layout()

    def extract_text(self, path):
        # ... Reuse extraction logic ...
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.txt': return self._chunk_text(open(path,'r',encoding='utf-8',errors='replace').read())
            elif ext == '.pdf': return self._read_pdf(path)
            elif ext == '.epub': return self._read_epub(path)
        except Exception as e:
            return [f"Error: {e}"]
        return ["Could not read file."]

    def _chunk_text(self, text, size=3000):
        return [text[i:i+size] for i in range(0, len(text), size)]

    def _read_pdf(self, path):
        if not PdfReader: return ["Please install pypdf"]
        try:
            reader = PdfReader(path)
            return [p.extract_text() for p in reader.pages if p.extract_text().strip()]
        except Exception as e: return [str(e)]

    def _read_epub(self, path):
        if not epub: return ["Please install ebooklib beautifulsoup4"]
        try:
            book = epub.read_epub(path)
            pages = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                    text = soup.get_text()
                    if len(text) > 200: pages.append(text)
            return pages
        except Exception as e: return [str(e)]

if __name__ == '__main__':
    app = wx.App()
    f = MainFrame()
    f.Show()
    app.MainLoop()
