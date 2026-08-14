#!/usr/bin/env python3
"""
Ollama连接测试脚本
用于验证本地Ollama服务是否正常工作
"""

import sys
import httpx

def test_ollama_connection(base_url="http://127.0.0.1:11434/v1"):
    """测试Ollama连接"""
    print(f"测试Ollama连接: {base_url}")
    
    try:
        # 测试模型列表
        client = httpx.Client(transport=httpx.HTTPTransport(http2=False), timeout=30)
        response = client.get(f"{base_url}/models")
        
        if response.status_code == 200:
            models = response.json()
            print(f"✓ 连接成功！")
            print(f"  可用模型:")
            for model in models.get('data', []):
                print(f"    - {model['id']}")
            return True
        else:
            print(f"✗ 连接失败，状态码: {response.status_code}")
            print(f"  响应: {response.text}")
            return False
    except Exception as e:
        print(f"✗ 连接异常: {e}")
        return False

def test_model_inference(model_name="qwen3:4b", base_url="http://127.0.0.1:11434/v1"):
    """测试模型推理"""
    print(f"\n测试模型推理: {model_name}")
    
    try:
        client = httpx.Client(transport=httpx.HTTPTransport(http2=False), timeout=60)
        response = client.post(
            f"{base_url}/chat/completions",
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "你好，请简要介绍一下你自己"}],
                "max_tokens": 100
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            print(f"✓ 推理成功！")
            print(f"  响应: {content[:100]}...")
            return True
        else:
            print(f"✗ 推理失败，状态码: {response.status_code}")
            print(f"  响应: {response.text}")
            return False
    except Exception as e:
        print(f"✗ 推理异常: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Ollama连接测试")
    print("=" * 50)
    
    # 测试连接
    conn_ok = test_ollama_connection()
    
    # 测试推理
    if conn_ok:
        test_model_inference()
    
    print("\n测试完成！")
