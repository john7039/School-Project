import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  // 개발 서버(npm run dev)에서만 쓰는 설정. 빌드 결과에는 영향이 없다.
  //
  // App.jsx 의 API 는 '' (같은 출처)다. 배포본은 nginx 가 /api 를 uvicorn 으로
  // 넘겨주므로 그대로 동작하지만, 개발 서버는 localhost:5173 이라 /api 를 받아줄
  // 백엔드가 없다. 화면은 뜨는데 데이터가 전부 비어 보인다.
  //
  // 여기서 /api 만 실제 서버로 넘겨주면, 노트북에 API 키도 파이썬도 DB 도
  // 없이 진짜 데이터를 보면서 화면을 고칠 수 있다.
  server: {
    proxy: {
      '/api': {
        target: 'https://macmini.tail1ca8bf.ts.net',
        changeOrigin: true,
      },
    },
  },
})
