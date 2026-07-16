# Windows Broadcast Management Client

這是一個用於控制 PORTech IS-670 IP Speaker 的 Windows Python GUI 系統。  
目前主要功能是透過 PJSUA 進行 SIP 撥號，並把預錄 WAV 音檔或即時麥克風聲音送到 IP Speaker。

目前系統流程：

```text
Python tkinter GUI -> PJSUA -> SIP/RTP G.711 PCMU -> PORTech IS-670
```

## 目前功能

- 使用 tkinter GUI 控制廣播
- 使用 PJSUA 撥打 IP Speaker
- 支援多台 Speaker 群組廣播
- 支援每台 Speaker 對同一個事件播放不同音檔
- 支援預錄語音播放後自動掛斷
- 支援即時廣播
- 支援音檔管理、錄音、本機測試播放
- 支援 IBS/IPB Server 註冊，讓 Speaker 主動註冊到本系統
- 關閉 GUI 時會嘗試停止 PJSUA、停止廣播、停止 IBS Server

## 資料夾結構

```text
ip_speaker/
|-- app.py
|-- audio_recorder.py
|-- config.json
|-- README.md
|-- requirements.txt
|-- run_demo.bat
|-- sip_registrar.py
|-- audio/
|-- logs/
|-- tools/
|   `-- pjsua/
|       `-- pjsua.exe
`-- sip_stacks/
    |-- pjsua/
    |   `-- backend.py
    `-- native/
```

## 執行方式

進入專案資料夾：

```powershell
cd C:\Users\user\Desktop\ip_speaker
python app.py
```

也可以直接執行：

```text
run_demo.bat
```

如果要使用 GUI 內建錄音功能，需要安裝：

```powershell
pip install sounddevice numpy
```

也可以直接執行：

```text
install_audio_deps.bat
```

## PJSUA 設定

PJSUA 已整合在專案內：

```text
tools/pjsua/pjsua.exe
```

`config.json` 內的設定：

```json
{
  "pjsua": {
    "path": "tools/pjsua/pjsua.exe"
  }
}
```

也就是說，之後整包 `ip_speaker` 搬到其他電腦時，不需要另外保留 `C:\sipbuild` 路徑。

## 重要網路設定

目前本機 SIP/RTP 使用的 IP：

```text
140.124.42.67
```

目前預設 Speaker IP：

```text
192.168.6.120
192.168.6.121
```

常用 port：

```text
IBS Server / SIP REGISTER: UDP 5060
PJSUA local SIP: UDP 64882 起跳
PJSUA local RTP: UDP 4004 起跳
```

多台 Speaker 廣播時，系統會自動幫每個 PJSUA process 分配不同 port：

```text
第 1 台：SIP 64882, RTP 4004
第 2 台：SIP 64884, RTP 4006
第 3 台：SIP 64886, RTP 4008
```

## 將 Speaker 註冊到系統

1. 先關閉會占用 UDP `5060` 的 SIP 軟體，例如 MicroSIP。
2. 開啟本系統 GUI。
3. 進入 `IBS Server` 頁面。
4. 按下 `啟動 IBS Server`。
5. 打開 Speaker 網頁，例如：

```text
http://192.168.6.120
```

6. 到 Speaker 的 `Service Domain Settings`。
7. 設定：

```text
Active: ON
User Name: 120
Register Name: 120
Register Password: 空白
IPB Server: 140.124.42.67
```

第二台可以設定：

```text
User Name: 121
Register Name: 121
IPB Server: 140.124.42.67
```

重點是每台 Speaker 的 `User Name` / `Register Name` 建議不要重複，方便系統辨識。

8. 按下 Speaker 網頁的 `Submit`。
9. 如果 Speaker 要求重開，請儲存後重開。
10. 確認 Speaker 頁面顯示：

```text
Registered
```

11. 回到 GUI 的 `IBS Server` 頁面。
12. 按 `重新整理註冊清單`。
13. 按 `匯入註冊 Speaker`。

匯入後，Speaker 會被寫入 `config.json` 的 `speakers`，並加入 `registered` 群組。

## Speaker 管理

在 `Speaker 管理` 頁面可以設定：

- Speaker 名稱
- Speaker IP
- SIP User
- SIP Port
- 預設音檔
- 每個事件要播放的音檔
- Speaker 群組

例如目前設定：

```json
"speakers": {
  "reg_120_192_168_6_120_5060": {
    "display_name": "platform_1",
    "ip": "192.168.6.120",
    "sip_user": "120",
    "sip_port": 5060,
    "audio_id": "testing",
    "event_audio_ids": {
      "testing": "Right"
    }
  }
}
```

代表 `platform_1` 這台 Speaker 在 `測試廣播` 事件時，會播放 `Right` 這個音檔設定。

## 群組管理

群組設定在 `speaker_groups`：

```json
"speaker_groups": {
  "registered": {
    "display_name": "已註冊 Speaker",
    "speaker_ids": [
      "reg_120_192_168_6_120_5060",
      "reg_121_192_168_6_121_5060"
    ]
  }
}
```

在 GUI 上選擇目標群組後，按下 Trigger 時，系統會對群組內所有 Speaker 同時廣播。

## 預錄語音廣播

音檔放在：

```text
audio/
```

建議 WAV 格式：

```text
8000 Hz
mono
16-bit PCM
.wav
```

操作流程：

```text
選擇目標群組
↓
按下 Trigger
↓
系統同時撥打群組內 Speaker
↓
每台 Speaker 播放自己設定的音檔
↓
播放完成後自動掛斷
```

目前 Trigger 頁面保留五個主要事件：

- 測試廣播
- 旅客跌倒
- 行李滾落
- 輪椅進入
- 旅客逗留

## 音檔管理

在 `音檔管理` 頁面可以：

- 新增音檔設定
- 刪除音檔設定
- 調整音檔順序
- 錄製新音檔
- 本機測試播放
- 停止本機播放

音檔設定格式：

```json
"audio_files": {
  "testing": {
    "display_name": "測試廣播",
    "filename": "testing.wav",
    "description": "確認 IP Speaker 是否可正常播放。"
  }
}
```

新增音檔時，請把 wav 檔放到：

```text
audio/
```

然後在 GUI 裡新增對應的 Audio ID、顯示名稱、檔名與描述。

## 錄製新音檔

1. 進入 `音檔管理`。
2. 輸入 Audio ID，例如：

```text
custom_warning_01
```

3. 輸入顯示名稱與描述。
4. 按 `開始錄音`。
5. 對 Windows 預設麥克風說話。
6. 按 `停止錄音並儲存`。

系統會產生：

```text
audio/custom_warning_01.wav
```

錄音格式：

```text
8000 Hz
mono
16-bit PCM
```

## 音量調整

GUI 上可調整播放音量：

```text
0% ~ 200%
```

系統不會修改原始 WAV，而是會在 `logs/` 產生暫時音量調整後的 wav。

## 即時廣播

在 GUI 上使用：

```text
開始即時廣播
停止即時廣播
```

即時廣播會使用 Windows 預設錄音裝置，除非你在 `config.json` 設定：

```json
"pjsua": {
  "capture_dev": ""
}
```

如果多台 Speaker 同時即時廣播，有些實體麥克風可能無法被多個 PJSUA process 同時開啟。正式使用時建議使用 VB-CABLE 或 VoiceMeeter 這類虛擬音訊裝置。

## 關閉程式

直接按 GUI 右上角關閉即可。

關閉時系統會嘗試：

1. 停止預錄音檔播放
2. 停止即時廣播
3. 停止 IBS Server
4. 關閉專案內殘留的 `tools/pjsua/pjsua.exe`

如果 `IBS Server` 無法啟動，錯誤訊息會顯示目前占用 UDP `5060` 的程式名稱、PID 與路徑。

## 常見問題

### IBS Server 啟動失敗

通常是 UDP `5060` 被其他程式占用。

常見占用者：

- MicroSIP
- 其他 SIP 軟體
- 之前殘留的測試 server

請依照錯誤訊息顯示的 PID 或程式名稱關閉該程式。

### PJSUA 無法啟動

請確認：

```text
tools/pjsua/pjsua.exe
```

是否存在。

### 撥號成功但沒有聲音

請確認：

- WAV 是否存在
- WAV 格式是否為 8000 Hz / mono / 16-bit PCM
- Speaker 音量是否開啟
- Speaker 是否註冊成功
- 目標群組是否選對
- 每台 Speaker 的事件音檔是否設定正確

### 即時廣播沒有聲音

請確認：

- Windows 預設麥克風是否正確
- Windows 麥克風權限是否開啟
- 麥克風是否被其他程式占用
- `pjsua.capture_dev` 是否設定錯誤

### 錄音功能不能用

請安裝：

```powershell
pip install sounddevice numpy
```

## 主要設定欄位

- `backend`：目前固定使用 `pjsua`
- `local.ip`：本機綁定 SIP/RTP 的 IP
- `local.advertise_ip`：寫入 SIP/SDP 的本機 IP
- `local.sip_port`：本機 SIP 起始 port
- `local.rtp_port`：本機 RTP 起始 port
- `local.audio_gain`：播放音量百分比
- `pjsua.path`：PJSUA 執行檔路徑
- `speakers`：Speaker 清單
- `speaker_groups`：Speaker 群組
- `selected_speaker_group`：GUI 預設選取群組
- `audio_files`：音檔設定
- `registrar.host`：IBS Server 綁定位址，通常為 `0.0.0.0`
- `registrar.port`：IBS Server port，通常為 `5060`

## Log 檔案

主要 log 位置：

```text
logs/gui.log
logs/pjsua_gui.log
logs/pjsua_live.log
logs/sip_registrar.log
logs/sip_registrations.json
```

多台 Speaker 廣播時，會產生個別 PJSUA log，例如：

```text
logs/pjsua_gui_reg_120_192_168_6_120_5060.log
logs/pjsua_gui_reg_121_192_168_6_121_5060.log
```

## 授權提醒

目前系統使用 PJSUA / PJSIP。

PJSIP / PJSUA 是 GPL / commercial dual license。  
Demo 與技術驗證可以先使用目前版本；如果未來要正式商用或閉源交付，請確認授權方式，或改用適合正式交付的 SIP stack。
