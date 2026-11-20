using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows.Forms;

class NoActCanvasDlg : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
}

class Canvas : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
  Rectangle btn = new Rectangle(40, 60, 220, 70);
  string mode = "";
  string workdir = "";
  Bitmap buf;
  TextBox dimsBox;
  TextBox pathBox;
  TextBox statusBox;

  [STAThread]
  static void Main(string[] args) {
    Application.EnableVisualStyles();
    string mode = ArgVal(args, "--mode", "");
    string workdir = ArgVal(args, "--workdir", Path.Combine(Path.GetTempPath(), "turbo-field"));
    Application.Run(new Canvas(mode, workdir));
  }

  static string ArgVal(string[] args, string key, string def) {
    for (int i = 0; i < args.Length - 1; i++)
      if (args[i] == key) return args[i + 1];
    return def;
  }

  static string SafeResolve(string root, string relOrName) {
    string r = Path.GetFullPath(root);
    Directory.CreateDirectory(r);
    string candidate = (relOrName ?? "").Trim();
    string p = Path.IsPathRooted(candidate) ? Path.GetFullPath(candidate) : Path.GetFullPath(Path.Combine(r, candidate));
    if (!p.StartsWith(r, StringComparison.OrdinalIgnoreCase))
      throw new InvalidOperationException("Path outside workdir");
    return p;
  }

  public Canvas() : this("", Path.Combine(Path.GetTempPath(), "turbo-field")) {}

  public Canvas(string mode, string workdir) {
    this.mode = mode;
    this.workdir = workdir;
    DoubleBuffered = true;
    StartPosition = FormStartPosition.Manual;
    Location = new Point(100, 100);

    if (mode == "paint") BuildPaint();
    else if (mode == "viewer") BuildViewer();
    else {
      Text = "TurboCanvas"; Width = 360; Height = 260;
      MouseDown += (s, e) => { if (btn.Contains(e.Location)) Text = "TurboCanvas clicked"; };
    }
  }

  void InitBitmap(int w, int h) {
    if (buf != null) buf.Dispose();
    buf = new Bitmap(w, h);
    using (var g = Graphics.FromImage(buf)) {
      g.Clear(Color.White);
      g.FillRectangle(Brushes.SteelBlue, 20, 20, Math.Max(40, w - 40), Math.Max(40, h - 40));
    }
  }

  void BuildPaint() {
    Text = "TurboCanvas - Draw"; Width = 540; Height = 320;
    InitBitmap(400, 300);
    dimsBox = new TextBox { Name = "txtDims", Left = 12, Top = 12, Width = 140, ReadOnly = true, AccessibleName = "Dimensions", Text = "400 x 300" };
    pathBox = new TextBox { Name = "txtPngPath", Left = 160, Top = 12, Width = 260, AccessibleName = "PNG path", Text = Path.Combine(workdir, "canvas.png") };
    var btnResize = new Button { Name = "btnResize", Text = "Resize...", Left = 12, Top = 46, Width = 100 };
    var btnSave = new Button { Name = "btnSavePng", Text = "Save PNG", Left = 120, Top = 46, Width = 100 };
    statusBox = new TextBox { Name = "txtPaintStatus", Left = 228, Top = 48, Width = 280, ReadOnly = true, AccessibleName = "Paint status", Text = "Ready" };

    btnResize.Click += (s, e) => {
      BeginInvoke((Action)(() => {
        var dlg = new NoActCanvasDlg { Text = "Resize Canvas", Width = 300, Height = 170, StartPosition = FormStartPosition.Manual, Location = new Point(160, 160) };
        var wBox = new TextBox { Name = "txtW", Left = 90, Top = 14, Width = 160, AccessibleName = "Width", Text = buf.Width.ToString() };
        var hBox = new TextBox { Name = "txtH", Left = 90, Top = 46, Width = 160, AccessibleName = "Height", Text = buf.Height.ToString() };
        var apply = new Button { Name = "btnApplyResize", Text = "Apply", Left = 90, Top = 84, Width = 90 };
        apply.Click += (_s, _e) => {
          int w, h;
          if (int.TryParse(wBox.Text, out w) && int.TryParse(hBox.Text, out h) && w > 0 && h > 0 && w <= 4096 && h <= 4096) {
            InitBitmap(w, h);
            dimsBox.Text = w + " x " + h;
            statusBox.Text = "Resized to " + w + " x " + h;
            dlg.Close();
          }
        };
        dlg.Controls.AddRange(new Control[] {
          new Label { Text = "Width", Left = 12, Top = 16, Width = 70 }, wBox,
          new Label { Text = "Height", Left = 12, Top = 48, Width = 70 }, hBox,
          apply
        });
        dlg.Show(this);
      }));
    };
    btnSave.Click += (s, e) => {
      string outPath = SafeResolve(workdir, pathBox.Text);
      buf.Save(outPath, ImageFormat.Png);
      statusBox.Text = "Saved " + buf.Width + " x " + buf.Height + " PNG";
    };
    Controls.AddRange(new Control[] { dimsBox, pathBox, btnResize, btnSave, statusBox });
  }

  void BuildViewer() {
    Text = "TurboCanvas - Viewer"; Width = 540; Height = 260;
    string defPng = SafeResolve(workdir, "canvas.png");
    if (!File.Exists(defPng)) {
      InitBitmap(800, 600);
      buf.Save(defPng, ImageFormat.Png);
    }
    pathBox = new TextBox { Name = "txtOpenPath", Left = 12, Top = 12, Width = 360, AccessibleName = "Image path", Text = defPng };
    var btnOpen = new Button { Name = "btnOpenImg", Text = "Open Image", Left = 380, Top = 10, Width = 120 };
    dimsBox = new TextBox { Name = "txtImgInfo", Left = 12, Top = 48, Width = 488, ReadOnly = true, AccessibleName = "Image dimensions", Text = "Not opened" };
    btnOpen.Click += (s, e) => {
      string p = SafeResolve(workdir, pathBox.Text);
      using (var im = Image.FromFile(p)) {
        dimsBox.Text = im.Width + " x " + im.Height + " PNG";
      }
    };
    Controls.AddRange(new Control[] { pathBox, btnOpen, dimsBox });
  }

  protected override void OnPaint(PaintEventArgs e) {
    if (mode == "paint" || mode == "viewer") {
      base.OnPaint(e);
      return;
    }
    e.Graphics.Clear(Color.White);
    e.Graphics.FillRectangle(Brushes.LightSteelBlue, btn);
    e.Graphics.DrawString("Save", new Font("Segoe UI", 28), Brushes.Black, btn.X + 50, btn.Y + 10);
  }
}
