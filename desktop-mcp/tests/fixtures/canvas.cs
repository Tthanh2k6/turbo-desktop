using System;
using System.Drawing;
using System.Windows.Forms;

class Canvas : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
  Rectangle btn = new Rectangle(40, 60, 220, 70);
  static void Main() { Application.Run(new Canvas()); }
  public Canvas() {
    Text = "TurboCanvas"; Width = 360; Height = 260; DoubleBuffered = true;
    StartPosition = FormStartPosition.Manual; Location = new Point(100, 100);
    MouseDown += (s, e) => { if (btn.Contains(e.Location)) Text = "TurboCanvas clicked"; };
  }
  protected override void OnPaint(PaintEventArgs e) {
    e.Graphics.Clear(Color.White);
    e.Graphics.FillRectangle(Brushes.LightSteelBlue, btn);
    e.Graphics.DrawString("Save", new Font("Segoe UI", 28), Brushes.Black, btn.X + 50, btn.Y + 10);
  }
}
