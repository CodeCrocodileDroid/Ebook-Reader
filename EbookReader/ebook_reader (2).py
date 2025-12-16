import wx
import wx.lib.newevent
import os
import threading
import pyttsx3
import warnings

# Suppress ebooklib warnings
warnings.filterwarnings("ignore", category=UserWarning, module='ebooklib')

# Optional libraries for formats
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
# Offline Services
# ---------------------------------------------------------------------------

class TTSService:
    """Handles Offline Text-to-Speech using pyttsx3."""
    def __init__(self):
        self.engine = None
        self.is_speaking = False
        try:
            self.engine = pyttsx3.init()
        except Exception as e:
            print(f"TTS Init failed: {e}")

    def speak(self, text):
        if not self.engine:
            return
        
        if self.is_speaking:
            self.stop()

        self.is_speaking = True
        
        threading.Thread(target=self._speak_thread, args=(text,)).start()

    def _speak_thread(self, text):
        try:
            # Re-init in thread for safety
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")
        finally:
            self.is_speaking = False

    def stop(self):
        if self.engine and self.is_speaking:
            self.engine.stop()
            self.is_speaking = False

# ---------------------------------------------------------------------------
# GUI Components
# ---------------------------------------------------------------------------

class NotesPanel(wx.Panel):
    """Sidebar panel for User Notes."""
    def __init__(self, parent):
        super().__init__(parent)
        
        sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, label="My Notes")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALL, 10)

        self.notes_area = wx.TextCtrl(self, style=wx.TE_MULTILINE)
        sizer.Add(self.notes_area, 1, wx.EXPAND | wx.ALL, 5)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        save_btn = wx.Button(self, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, self.on_save)
        btn_sizer.Add(save_btn, 0, wx.RIGHT, 5)
        
        clear_btn = wx.Button(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        btn_sizer.Add(clear_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        self.notes_area.SetValue("Notes are kept in memory for this session.")

    def on_save(self, event):
        wx.MessageBox("Notes saved to memory!", "Success", wx.OK)

    def on_clear(self, event):
        self.notes_area.Clear()


class ReaderPanel(wx.Panel):
    """Main reading area with Page Flipping support."""
    def __init__(self, parent, tts_service):
        super().__init__(parent)
        self.tts_service = tts_service
        self.pages = []
        self.current_page_idx = 0
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- Top Toolbar ---
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        open_btn = wx.Button(self, label="📂 Open")
        open_btn.Bind(wx.EVT_BUTTON, self.on_open_file)
        toolbar_sizer.Add(open_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.read_btn = wx.Button(self, label="🔊 Read Page")
        self.read_btn.Bind(wx.EVT_BUTTON, self.on_read_aloud)
        toolbar_sizer.Add(self.read_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        stop_btn = wx.Button(self, label="⏹ Stop")
        stop_btn.Bind(wx.EVT_BUTTON, self.on_stop_read)
        toolbar_sizer.Add(stop_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        # Navigation
        self.prev_btn = wx.Button(self, label="< Prev")
        self.prev_btn.Bind(wx.EVT_BUTTON, self.on_prev_page)
        self.prev_btn.Disable()
        toolbar_sizer.Add(self.prev_btn, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 20)

        self.page_lbl = wx.StaticText(self, label="0/0")
        toolbar_sizer.Add(self.page_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)

        self.next_btn = wx.Button(self, label="Next >")
        self.next_btn.Bind(wx.EVT_BUTTON, self.on_next_page)
        self.next_btn.Disable()
        toolbar_sizer.Add(self.next_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)

        self.title_lbl = wx.StaticText(self, label="No Book Loaded")
        # Flexible spacer to push title to right or keep it near
        toolbar_sizer.AddStretchSpacer(1) 
        toolbar_sizer.Add(self.title_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        sizer.Add(toolbar_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        # --- Text Area ---
        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL | wx.TE_RICH2)
        font = wx.Font(14, wx.FONTFAMILY_ROMAN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Georgia")
        self.text_ctrl.SetFont(font)
        self.text_ctrl.SetMargins(30, 30)
        
        sizer.Add(self.text_ctrl, 1, wx.EXPAND)

        self.SetSizer(sizer)

    def on_open_file(self, event):
        wildcard = "eBooks (*.txt;*.pdf;*.epub)|*.txt;*.pdf;*.epub"
        with wx.FileDialog(self, "Open eBook", wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            self._load_file(pathname)

    def _load_file(self, pathname):
        wx.BeginBusyCursor()
        try:
            ext = os.path.splitext(pathname)[1].lower()
            new_pages = []
            
            if ext == '.txt':
                new_pages = self._read_txt_pages(pathname)
            elif ext == '.pdf':
                new_pages = self._read_pdf_pages(pathname)
            elif ext == '.epub':
                new_pages = self._read_epub_pages(pathname)
            else:
                new_pages = ["Unsupported file format."]

            if not new_pages:
                new_pages = ["(Empty Book or Extraction Failed)"]

            self.pages = new_pages
            self.current_page_idx = 0
            self.title_lbl.SetLabel(os.path.basename(pathname))
            self._update_display()
            
        except Exception as e:
            wx.LogError(f"Cannot open file: {e}")
            self.pages = [f"Error loading file: {e}"]
            self.current_page_idx = 0
            self._update_display()
        finally:
            wx.EndBusyCursor()

    def _read_txt_pages(self, path):
        # Chunk text file by ~3000 chars
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        chunk_size = 3000
        return [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

    def _read_pdf_pages(self, path):
        if not PdfReader:
            return ["Library missing: pypdf"]
        try:
            reader = PdfReader(path)
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt.strip():
                    pages_text.append(txt)
            return pages_text if pages_text else ["No text found in PDF."]
        except Exception as e:
            return [f"Error reading PDF: {e}"]

    def _read_epub_pages(self, path):
        if not epub or not BeautifulSoup:
            return ["Libraries missing: ebooklib, beautifulsoup4"]
        try:
            book = epub.read_epub(path)
            pages_text = []
            
            # Add Title Page
            title_meta = book.get_metadata('DC', 'title')
            if title_meta:
                 pages_text.append(f"Title: {title_meta[0][0]}")

            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                    text = soup.get_text()
                    if len(text.strip()) > 100:
                        # Chunk long chapters
                        chunk_size = 3000
                        if len(text) > chunk_size:
                            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
                            pages_text.extend(chunks)
                        else:
                            pages_text.append(text)
            return pages_text
        except Exception as e:
             return [f"Error reading EPUB: {e}"]

    def _update_display(self):
        total = len(self.pages)
        if total == 0:
            self.text_ctrl.SetValue("")
            self.page_lbl.SetLabel("0/0")
            self.prev_btn.Disable()
            self.next_btn.Disable()
            return

        # Ensure index is within bounds
        self.current_page_idx = max(0, min(self.current_page_idx, total - 1))
        
        content = self.pages[self.current_page_idx]
        self.text_ctrl.SetValue(content)
        self.text_ctrl.SetInsertionPoint(0) # Scroll to top
        
        self.page_lbl.SetLabel(f"{self.current_page_idx + 1} / {total}")
        
        # Update buttons
        self.prev_btn.Enable(self.current_page_idx > 0)
        self.next_btn.Enable(self.current_page_idx < total - 1)

    def on_prev_page(self, event):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.tts_service.stop()
            self._update_display()

    def on_next_page(self, event):
        if self.current_page_idx < len(self.pages) - 1:
            self.current_page_idx += 1
            self.tts_service.stop()
            self._update_display()

    def on_read_aloud(self, event):
        if not self.pages: return
        
        selection = self.text_ctrl.GetStringSelection()
        if selection:
            self.tts_service.speak(selection)
        else:
            # Read current page content
            content = self.pages[self.current_page_idx]
            self.tts_service.speak(content)

    def on_stop_read(self, event):
        self.tts_service.stop()


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Offline Reader (Page View)", size=(1100, 750))

        self.tts_service = TTSService()
        self.splitter = wx.SplitterWindow(self)
        self.reader_panel = ReaderPanel(self.splitter, self.tts_service)
        self.notes_panel = NotesPanel(self.splitter)

        self.splitter.SplitVertically(self.reader_panel, self.notes_panel)
        self.splitter.SetMinimumPaneSize(250)
        self.splitter.SetSashGravity(0.75)

        self.CreateStatusBar()
        self.SetStatusText("Ready - Load a TXT, PDF or EPUB file to start reading")

if __name__ == '__main__':
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
