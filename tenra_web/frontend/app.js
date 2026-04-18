const chat = document.getElementById('chat');
const form = document.getElementById('chat-form');
const promptInput = document.getElementById('prompt');
const sendBtn = document.getElementById('send-btn');
const permissionControl = document.getElementById('permission-control');
const permissionScreen = document.getElementById('permission-screen');
const screenPreview = document.getElementById('screen-preview');
const screenStatus = document.getElementById('screen-status');

let messageHistory = [];
let latestScreenFrame = null;
let screenPollTimer = null;

function addMessageToUI(content, sender = 'tenra', isHTML = false) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender);
    
    if (isHTML) {
        msgDiv.innerHTML = content;
    } else {
        msgDiv.textContent = content;
    }
    
    chat.appendChild(msgDiv);
    chat.scrollTop = chat.scrollHeight;
    return msgDiv;
}

function addCodeBlock(status, code, output) {
    const codeDiv = document.createElement('div');
    codeDiv.classList.add('code-execution');
    
    if (status === 'running') {
        codeDiv.classList.add('running');
        codeDiv.innerHTML = `
            <div class="code-header">
                <div class="code-spinner"></div>
                <span>Kod Çalıştırılıyor...</span>
            </div>
            <pre class="code-content"><code>${escapeHtml(code || '')}</code></pre>
        `;
    } else if (status === 'success') {
        codeDiv.classList.add('success');
        codeDiv.innerHTML = `
            <div class="code-header success-header">
                <span>✓ Başarıyla Çalıştırıldı</span>
            </div>
            <pre class="code-output">${escapeHtml(output || '(Çıktı yok)')}</pre>
        `;
    } else {
        codeDiv.classList.add('error');
        codeDiv.innerHTML = `
            <div class="code-header error-header">
                <span>✗ Hata Oluştu</span>
            </div>
            <pre class="code-output error-text">${escapeHtml(output || '')}</pre>
        `;
    }
    
    chat.appendChild(codeDiv);
    chat.scrollTop = chat.scrollHeight;
    return codeDiv;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

async function pollScreenFrame() {
    if (!permissionScreen.checked) {
        return;
    }

    try {
        const response = await fetch('/screen');
        const data = await response.json();
        if (data.ok && data.image) {
            screenPreview.src = data.image;
            latestScreenFrame = data.image.replace(/^data:image\/jpeg;base64,/, '');
            screenStatus.textContent = 'Canlı';
        } else {
            screenStatus.textContent = 'Erişim yok';
        }
    } catch (error) {
        screenStatus.textContent = 'Bağlantı hatası';
    }
}

function startScreenPolling() {
    if (screenPollTimer) clearInterval(screenPollTimer);

    if (!permissionScreen.checked) {
        latestScreenFrame = null;
        screenPreview.removeAttribute('src');
        screenStatus.textContent = 'Kapalı';
        return;
    }

    screenStatus.textContent = 'Bağlanıyor...';
    pollScreenFrame();
    screenPollTimer = setInterval(pollScreenFrame, 2500);
}

permissionScreen.addEventListener('change', startScreenPolling);
startScreenPolling();

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = promptInput.value.trim();
    if (!text) return;
    
    addMessageToUI(text, 'user');
    messageHistory.push({ role: 'user', content: text });
    
    promptInput.value = '';
    promptInput.disabled = true;
    sendBtn.disabled = true;

    const tenraMsgDiv = addMessageToUI('', 'tenra');
    let fullResponse = '';
    let currentRunningBlock = null;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: messageHistory,
                permissions: {
                    control: permissionControl.checked,
                    screen: permissionScreen.checked
                },
                screenFrame: permissionScreen.checked ? latestScreenFrame : null
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunks = decoder.decode(value, { stream: true }).split('\n');
            
            for (const chunk of chunks) {
                if (!chunk.trim()) continue;
                try {
                    const data = JSON.parse(chunk);
                    
                    if (data.type === 'content') {
                        fullResponse += data.content;
                        // Kod bloklarını gizleyerek göster (çünkü bunlar ayrıca çalıştırılacak)
                        let displayText = fullResponse.replace(/```python[\s\S]*?```/g, '\n*(Kod çalıştırılıyor...)*\n');
                        tenraMsgDiv.innerHTML = marked.parse(displayText);
                        chat.scrollTop = chat.scrollHeight;
                    } 
                    else if (data.type === 'code_exec') {
                        if (data.status === 'running') {
                            currentRunningBlock = addCodeBlock('running', data.code, null);
                        } else if (data.status === 'blocked') {
                            if (currentRunningBlock) {
                                currentRunningBlock.remove();
                                currentRunningBlock = null;
                            }
                            addCodeBlock('error', null, data.output || 'Kontrol izni olmadığı için engellendi.');
                        } else {
                            // Eski 'running' bloğunu kaldır
                            if (currentRunningBlock) {
                                currentRunningBlock.remove();
                                currentRunningBlock = null;
                            }
                            addCodeBlock(data.status, null, data.output);
                        }
                    }
                    else if (data.type === 'error') {
                        addMessageToUI("⚠️ " + data.content, 'tenra');
                    }
                    
                } catch (err) {
                    // non-JSON line, ignore
                }
            }
        }
        
        if (fullResponse) {
            messageHistory.push({ role: 'assistant', content: fullResponse });
        }

    } catch (error) {
        addMessageToUI("Bağlantı hatası oluştu.", 'tenra');
    } finally {
        promptInput.disabled = false;
        sendBtn.disabled = false;
        promptInput.focus();
        chat.scrollTop = chat.scrollHeight;
    }
});
