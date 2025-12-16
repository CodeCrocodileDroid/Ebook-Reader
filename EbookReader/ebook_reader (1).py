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
        
        # TTS engine block the loop, so we run it in a thread
        threading.Thread(target=self._speak_thread, args=(text,)).start()

    def _speak_thread(self, text):
        try:
            # We need a new engine instance for the thread or careful locking
            # pyttsx3 is tricky with threads. 
            # Safe approach: Run the loop inside the thread.
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
        save_btn = wx.Button(self, label="Save Notes (Local)")
        save_btn.Bind(wx.EVT_BUTTON, self.on_save)
        btn_sizer.Add(save_btn, 0, wx.RIGHT, 5)
        
        clear_btn = wx.Button(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        btn_sizer.Add(clear_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        
        self.notes_area.SetValue("Use this space to take notes on your book.\n\nNotes are kept in memory for this session.")

    def on_save(self, event):
        wx.MessageBox("Notes saved to memory!", "Success", wx.OK)

    def on_clear(self, event):
        self.notes_area.Clear()


class ReaderPanel(wx.Panel):
    """Main reading area with support for TXT, PDF, EPUB."""
    def __init__(self, parent, tts_service):
        super().__init__(parent)
        self.tts_service = tts_service
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        open_btn = wx.Button(self, label="📂 Open eBook")
        open_btn.Bind(wx.EVT_BUTTON, self.on_open_file)
        toolbar_sizer.Add(open_btn, 0, wx.ALL, 5)

        self.read_btn = wx.Button(self, label="🔊 Read Aloud")
        self.read_btn.Bind(wx.EVT_BUTTON, self.on_read_aloud)
        toolbar_sizer.Add(self.read_btn, 0, wx.ALL, 5)

        stop_btn = wx.Button(self, label="⏹ Stop")
        stop_btn.Bind(wx.EVT_BUTTON, self.on_stop_read)
        toolbar_sizer.Add(stop_btn, 0, wx.ALL, 5)
        
        self.title_lbl = wx.StaticText(self, label="No Book Loaded")
        toolbar_sizer.Add(self.title_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        sizer.Add(toolbar_sizer, 0, wx.EXPAND)

        # Text Area
        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL | wx.TE_RICH2)
        font = wx.Font(12, wx.FONTFAMILY_ROMAN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Georgia")
        self.text_ctrl.SetFont(font)
        self.text_ctrl.SetMargins(20, 20)
        
        # Search Bar
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_lbl = wx.StaticText(self, label="Search:")
        self.search_box = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        search_btn = wx.Button(self, label="Find Next")
        search_btn.Bind(wx.EVT_BUTTON, self.on_search)

        search_sizer.Add(search_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        search_sizer.Add(self.search_box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        search_sizer.Add(search_btn, 0, wx.RIGHT, 5)

        sizer.Add(self.text_ctrl, 1, wx.EXPAND)
        sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)

    def on_open_file(self, event):
        wildcard = "eBooks (*.txt;*.pdf;*.epub)|*.txt;*.pdf;*.epub|Text (*.txt)|*.txt|PDF (*.pdf)|*.pdf|EPUB (*.epub)|*.epub"
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
            content = ""
            
            if ext == '.txt':
                with open(pathname, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            elif ext == '.pdf':
                content = self._read_pdf(pathname)
            elif ext == '.epub':
                content = self._read_epub(pathname)
            else:
                content = "Unsupported file format."

            self.text_ctrl.SetValue(content)
            self.title_lbl.SetLabel(os.path.basename(pathname))
        except Exception as e:
            wx.LogError(f"Cannot open file: {e}")
        finally:
            wx.EndBusyCursor()

    def _read_pdf(self, path):
        if not PdfReader:
            wx.CallAfter(wx.MessageBox, "pypdf library missing. Run: pip install pypdf", "Error", wx.ICON_ERROR)
            return "Library missing: pypdf"
        try:
            reader = PdfReader(path)
            text = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text.append(extracted)
            return "\n".join(text)
        except Exception as e:
            return f"Error reading PDF: {e}"

    def _read_epub(self, path):
        if not epub or not BeautifulSoup:
            wx.CallAfter(wx.MessageBox, "Libraries missing. Run: pip install ebooklib beautifulsoup4", "Error", wx.ICON_ERROR)
            return "Library missing: ebooklib or beautifulsoup4"
        try:
            book = epub.read_epub(path)
            text = []
            # Attempt to get title
            title_meta = book.get_metadata('DC', 'title')
            if title_meta:
                 text.append(f"Title: {title_meta[0][0]}\n")
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                    text.append(soup.get_text())
            return "\n\n".join(text)
        except Exception as e:
             return f"Error reading EPUB: {e}"

    def get_content(self):
        return self.text_ctrl.GetValue()

    def on_read_aloud(self, event):
        selection = self.text_ctrl.GetStringSelection()
        if selection:
            self.tts_service.speak(selection)
        else:
            full_text = self.text_ctrl.GetValue()
            pos = self.text_ctrl.GetInsertionPoint()
            # Limit initial read buffer if very long to prevent lag
            self.tts_service.speak(full_text[pos:pos+5000])

    def on_stop_read(self, event):
        self.tts_service.stop()

    def on_search(self, event):
        query = self.search_box.GetValue()
        if not query:
            return
        
        full_text = self.text_ctrl.GetValue().lower()
        query = query.lower()
        
        start_pos = self.text_ctrl.GetInsertionPoint()
        found_pos = full_text.find(query, start_pos + 1)
        
        if found_pos == -1:
             found_pos = full_text.find(query, 0)

        if found_pos != -1:
            self.text_ctrl.SetInsertionPoint(found_pos)
            self.text_ctrl.SetSelection(found_pos, found_pos + len(query))
            self.text_ctrl.SetFocus()
        else:
            wx.MessageBox("Text not found.", "Search", wx.OK | wx.ICON_INFORMATION)


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Offline Reader (TXT, PDF, EPUB)", size=(1000, 700))

        self.tts_service = TTSService()
        self.splitter = wx.SplitterWindow(self)
        self.reader_panel = ReaderPanel(self.splitter, self.tts_service)
        self.notes_panel = NotesPanel(self.splitter)

        self.splitter.SplitVertically(self.reader_panel, self.notes_panel)
        self.splitter.SetMinimumPaneSize(250)
        self.splitter.SetSashGravity(0.7)

        self.CreateStatusBar()
        self.SetStatusText("Ready - Offline Mode")

if __name__ == '__main__':
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
