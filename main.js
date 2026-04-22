const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let pyProc = null;
let mainWindow = null;

function getPythonPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend', 'main');
  }
  return path.join(__dirname, '..', 'backend', 'venv', 'Scripts', 'python');
}

function getBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }
  return path.join(__dirname, '..', 'backend');
}

function startPythonBackend() {
  const pyPath = getPythonPath();
  const backendDir = getBackendPath();

  pyProc = spawn(pyPath, ['-m', 'uvicorn', 'main:app', '--port', '8765'], {
    cwd: backendDir,
    env: { ...process.env },
  });

  pyProc.stdout.on('data', (data) => {
    console.log(`[Python] ${data}`);
  });

  pyProc.stderr.on('data', (data) => {
    console.error(`[Python] ${data}`);
  });

  pyProc.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    pyProc = null;
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1280,
    minHeight: 800,
    title: 'DropNest',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devServerURL = 'http://localhost:5173';
  const prodPath = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');

  if (!app.isPackaged) {
    mainWindow.loadURL(devServerURL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(prodPath);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  startPythonBackend();

  setTimeout(() => {
    createWindow();
  }, 2000);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pyProc) {
    pyProc.kill();
    pyProc = null;
  }
});
