"""Add showOnWorkbench call to pho-index.html after processing succeeds."""
path = r'c:\Users\shenf\Desktop\virtual_tryon\pho-index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_text = """        uploadStatus.textContent = `\u2705 \u5b8c\u6210\uff01\u7eb9\u7406\u5df2\u751f\u6210\u5e76\u52a0\u5165\u8863\u6a71`;
        uploadStatus.className = 'success';
        btnAnalyze.disabled = false;
        btnProcess.disabled = false;
      } catch (err) {"""

new_text = """        uploadStatus.textContent = `\u2705 \u5b8c\u6210\uff01\u7eb9\u7406\u5df2\u751f\u6210\u5e76\u52a0\u5165\u8863\u6a71`;
        uploadStatus.className = 'success';
        btnAnalyze.disabled = false;
        btnProcess.disabled = false;
        // Auto-show workbench
        if (typeof showOnWorkbench === 'function') {
          const segName = data.seg_pic_url.split('/').pop();
          showOnWorkbench(segPicUrl, segName, clothingType);
        }
      } catch (err) {"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Done: showOnWorkbench added')
else:
    print('Pattern not found')
    idx = content.find('uploadStatus.className')
    print(f'uploadStatus.className found at: {idx}')
    print(content[idx:idx+300])
