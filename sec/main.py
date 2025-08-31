import os
import httpx
import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from watermark import generate_watermark_content, text_to_binary, encode_watermark, WatermarkInjector, verify_watermark

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量获取配置
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "https://api.openai.com/v1")
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY")

if not UPSTREAM_API_KEY:
    raise ValueError("UPSTREAM_API_KEY is not set in the environment variables.")

app = FastAPI(title="LLM Watermark Reverse Proxy")
client = httpx.AsyncClient(base_url=UPSTREAM_URL)

@app.post("/v1/chat/completions")
async def chat_completions_proxy(request: Request):
    """
    代理 /v1/chat/completions 请求，并添加水印
    """
    # 1. 解析请求体
    request_data = await request.json()
    is_stream = request_data.get("stream", False)

    # 2. 准备向上游发送的请求
    headers = {
        "Authorization": f"Bearer {UPSTREAM_API_KEY}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("Accept", "application/json"),
    }
    
    # 3. 生成水印
    user_id = request.headers.get("x-user-id", "user-from-proxy") 
    watermark_content = generate_watermark_content(user_id=user_id)
    binary_watermark = text_to_binary(watermark_content)
    encoded_watermark = encode_watermark(binary_watermark)
    
    # 4. 根据是否为流式请求，进行不同处理
    async def process_stream_response():
        """处理流式响应，逐块注入水印"""
        injector = WatermarkInjector(encoded_watermark, interval=5)
        async with client.stream("post", "/chat/completions", json=request_data, headers=headers, timeout=600) as response:
            async for chunk in response.aiter_bytes():
                chunk_str = chunk.decode('utf-8')
                if chunk_str.strip().startswith("data:"):
                    # 移除 "data: " 前缀和末尾的换行
                    content_json_str = chunk_str.strip()[5:].strip()
                    if content_json_str == "[DONE]":
                        yield chunk
                        continue
                    
                    try:
                        data = json.loads(content_json_str)
                        # 获取文本内容
                        text_content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if text_content:
                            # 注入水印
                            injected_content = injector.inject(text_content)
                            data["choices"][0]["delta"]["content"] = injected_content
                            # 重新构建 SSE 块
                            new_chunk_str = f"data: {json.dumps(data)}\n\n"
                            yield new_chunk_str.encode('utf-8')
                        else:
                            yield chunk # 如果没有文本内容，则原样返回
                    except json.JSONDecodeError:
                        yield chunk # 如果JSON解析失败，原样返回
                else:
                    yield chunk # 非 data 块，原样返回

    if is_stream:
        return StreamingResponse(process_stream_response(), media_type="text/event-stream")
    else:
        # 处理非流式响应
        response = await client.post("/chat/completions", json=request_data, headers=headers, timeout=600)
        response_data = response.json()
        
        # 在返回的文本中注入水印
        if "choices" in response_data and len(response_data["choices"]) > 0:
            full_text = response_data["choices"][0].get("message", {}).get("content", "")
            if full_text:
                injector = WatermarkInjector(encoded_watermark, interval=5)
                injected_text = injector.inject(full_text)
                response_data["choices"][0]["message"]["content"] = injected_text
        
        return Response(
            content=json.dumps(response_data),
            status_code=response.status_code,
            media_type="application/json",
        )

@app.post("/v1/verify-watermark")
async def verify_watermark_endpoint(request: Request):
    """
    一个用于测试水印验证的端点
    """
    data = await request.json()
    text = data.get("text")
    if not text:
        return {"error": "Text field is required."}
    
    result = verify_watermark(text)
    return result

if __name__ == "__main__":
    import uvicorn
    # 启动服务器，监听 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
