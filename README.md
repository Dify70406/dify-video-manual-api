# dify-video-manual-api

## 概要
動画から画像を抽出し、difyで手順書を生成するためのAPI

## エンドポイント
POST /manual

## リクエスト
{
  "video_url": "https://..."
}

## レスポンス
{
  "transcript": "...",
  "images": ["url1", "url2"]
}

## 技術
- Flask
- Cloud Run
- OpenCV
- yt-dlp
- GCS

## 備考
手順生成はdify側で行う
