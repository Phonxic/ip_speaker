# IP Speaker Demo Control

[!IMPORTANT]
## 完整版 Demo 請使用 `PythonGUI+PJSIP` 分支
目前 `main` 分支是使用 **Python tkinter + MicroSIP** 的早期測試版本。
真正完整的 Demo 位於 **`PythonGUI+PJSIP`** 分支，該版本已整合 Python GUI 與 PJSIP，不需要透過 MicroSIP 操作。
請使用以下指令直接下載完整版本：
```powershell
git clone --branch "PythonGUI+PJSIP" --single-branch https://github.com/Phonxic/ip_speaker.git
cd ip_speaker
```
專案分支頁面：
https://github.com/Phonxic/ip_speaker/tree/PythonGUI%2BPJSIP
若使用一般的 `git clone`，預設會下載目前的 `main` 分支，而不是完整的 PJSIP Demo。

## 關於此分支

這個 `main` 分支是一個 Windows Python tkinter Demo，用來控制 PORTech IS-670 IP Speaker。

程式會透過 Windows `start` 指令開啟 SIP URI，讓系統交給 MicroSIP 撥號；預錄語音播放使用 Python 內建 `winsound`，不需要額外套件。

此分支主要保留作為 MicroSIP 測試版本。若要使用完整的 Python GUI + PJSIP Demo，請切換至 `PythonGUI+PJSIP` 分支。

這是一個 Windows Python tkinter Demo，用來控制 PORTech IS-670 IP Speaker。程式會透過 Windows `start` 指令開啟 SIP URI，讓系統交給 MicroSIP 撥號；預錄語音播放使用 Python 內建 `winsound`，不需要額外套件。

## 專案結構

```text
ip_speaker_demo/
├── app.py
├── config.json
├── README.md
└── audio/
    ├── testing.wav
    ├── fall_warning.wav
    ├── baggage_warning.wav
    ├── wheelchair_warning.wav
    └── stay_warning.wav
```

## 如何執行

1. 確認電腦已安裝 Python 3。
2. 確認 MicroSIP 已安裝完成。
3. 確認手動用 MicroSIP 撥打 `sip:4267@192.168.6.120` 可以成功連線。
4. 在 PowerShell 進入專案資料夾：

```powershell
cd C:\Users\user\Desktop\ip_speaker_demo
python app.py
```

## config.json 設定

`config.json` 會在不存在時自動建立。預設內容如下：

```json
{
  "sip_uri": "sip:4267@192.168.6.120",
  "microsip_paths": [
    "C:\\Program Files\\MicroSIP\\microsip.exe",
    "C:\\Program Files (x86)\\MicroSIP\\microsip.exe"
  ],
  "audio_files": {
    "test_warning": "testing.wav",
    "fall_warning": "fall_warning.wav",
    "baggage_warning": "baggage_warning.wav",
    "wheelchair_warning": "wheelchair_warning.wav",
    "stay_warning": "stay_warning.wav"
  }
}
```

- `sip_uri`：IP Speaker 的 SIP URI。
- `microsip_paths`：按下「開啟 MicroSIP」時會依序檢查的 MicroSIP 執行檔路徑。
- `audio_files`：預錄語音按鈕對應的 WAV 檔名。

## 如何放音檔

請將 WAV 音檔放在 `audio` 資料夾，檔名需與 `config.json` 內設定一致。

如果音檔不存在，程式不會當掉，GUI 會顯示「找不到音檔」並跳出錯誤訊息。

## MicroSIP 麥克風設定差異

人員通話廣播與預錄語音廣播需要的 MicroSIP 麥克風來源不同：

- 人員通話廣播：請確認 MicroSIP 麥克風來源為實體麥克風，或已將實體麥克風導入 `CABLE Output`。
- 預錄語音廣播：請確認 MicroSIP 麥克風來源為 `Stereo Mix` 或 `CABLE Output`，讓電腦播放的音檔能送進 MicroSIP。

若要同時支援人聲與預錄音檔，建議使用 VB-CABLE，並讓 MicroSIP 麥克風固定為 `CABLE Output`。實體麥克風與電腦播放音訊可再透過系統音訊路由或混音工具導入 VB-CABLE。

## 人員通話廣播流程

1. 開啟 MicroSIP。
2. 將 MicroSIP 麥克風來源設定為實體麥克風，或設定為已接收實體麥克風的 `CABLE Output`。
3. 按下「開始通話廣播」。
4. 程式會用 Windows `start` 指令開啟 `sip:4267@192.168.6.120`。
5. MicroSIP 連線成功後，請直接對麥克風說話。
6. 要結束時按下「結束通話廣播」，再依照提示到 MicroSIP 中按下掛斷。

## 預錄語音廣播流程

1. 開啟 MicroSIP。
2. 將 MicroSIP 麥克風來源設定為 `Stereo Mix` 或 `CABLE Output`。
3. 按下「連線 IP Speaker」。
4. 等 MicroSIP 完成撥號並連線。
5. 按下任一預錄語音按鈕：
   - 「播放：測試廣播」
   - 「播放：旅客跌倒」
   - 「播放：行李滾落」
   - 「播放：輪椅進入」
   - 「播放：旅客逗留」
6. 需要中止音檔時，按下「停止播放音檔」。
7. 要結束通話時，請在 MicroSIP 中手動按下掛斷。

## Demo 操作步驟

1. 執行 `python app.py`。
2. 在「連線控制」區塊按下「開啟 MicroSIP」。
3. 依照要測試的情境設定 MicroSIP 麥克風來源。
4. 人員通話廣播時，使用「人員通話廣播」區塊的「開始通話廣播」與「結束通話廣播」。
5. 預錄語音廣播時，先按「連線 IP Speaker」，再使用「預錄語音廣播」區塊播放音檔。
6. 若要替換音檔，按下「開啟音訊資料夾」，把 WAV 檔放入 `audio` 資料夾並確認檔名符合 `config.json`。
