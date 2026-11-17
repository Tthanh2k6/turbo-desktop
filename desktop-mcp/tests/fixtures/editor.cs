using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

class KeyBlocker : IMessageFilter {
  // Tests run on the owner's live PC: swallow real keyboard input unless started with --accept-keys,
  // so stray keystrokes from the owner never land in the fixture. UIA SetValue does not use key messages.
  public bool PreFilterMessage(ref Message m) { return m.Msg >= 0x100 && m.Msg <= 0x109; }
}

class Editor : Form {
  TextBox box;
  protected override bool ShowWithoutActivation { get { return true; } }
  [STAThread] static void Main(string[] args) { if (Array.IndexOf(args, "--accept-keys") < 0) Application.AddMessageFilter(new KeyBlocker());  Application.EnableVisualStyles(); Application.Run(new Editor()); }
  public Editor() {
    Text = "TurboEditor - Untitled";
    var cmd = Environment.GetCommandLineArgs();
    for (int i = 1; i < cmd.Length - 1; i++) if (cmd[i] == "--title") Text = cmd[i + 1]; Width = 600; Height = 400;
    StartPosition = FormStartPosition.Manual; Location = new Point(80, 80);
    var ms = new MenuStrip();
    var file = new ToolStripMenuItem("File");
    var save = new ToolStripMenuItem("Save As...") { ShortcutKeys = Keys.Control | Keys.S };
    save.Click += (s, e) => {
      using (var d = new SaveFileDialog()) {
        d.Filter = "Text|*.txt|All|*.*"; d.Title = "Save As";
        if (d.ShowDialog(this) == DialogResult.OK) { File.WriteAllText(d.FileName, box.Text); Text = "TurboEditor - " + Path.GetFileName(d.FileName); }
      }
    };
    file.DropDownItems.Add(save); ms.Items.Add(file);
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor", ScrollBars = ScrollBars.Vertical };
    Controls.Add(box); Controls.Add(ms); MainMenuStrip = ms;
  }
}
