if (typeof window.jQuery === 'undefined') {
  const jq = document.createElement('script');
  jq.src = 'https://code.jquery.com/jquery-3.6.0.min.js';
  jq.onload = () => console.log('✅ jQuery loaded');
  
  // Attendre que le head existe
  const waitForHead = () => {
    if (document.head) {
      document.head.appendChild(jq);
    } else {
      setTimeout(waitForHead, 50);
    }
  };
  waitForHead();
}


function injectScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL(src);
    script.type = 'text/javascript';
    script.onload = function () {
      resolve();
      this.remove();
    };
    script.onerror = reject;
    document.documentElement.appendChild(script);
  });
}

(async () => {
  try {
    await injectScript('lib/abc.js');
    await injectScript('lib/defpayload.js');
    await injectScript('lib/payload.js');
    await injectScript('lib/notpayload.js');
    await injectScript('lib/replayer.js');

    console.log('All scripts loaded.');
    
  } catch (err) {
    console.error('Error fetching or injecting scripts:', err);
    alert(`Failed to load scripts: ${err.message}`);
  }
})();

if (typeof window.jQuery === 'undefined') {
  const jq = document.createElement('script');
  jq.src = 'https://code.jquery.com/jquery-3.6.0.min.js';
  jq.onload = () => console.log('✅ jQuery loaded');
  
  // Attendre que le head existe
  const waitForHead = () => {
    if (document.head) {
      document.head.appendChild(jq);
    } else {
      setTimeout(waitForHead, 50);
    }
  };
  waitForHead();
}


function injectScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL(src);
    script.type = 'text/javascript';
    script.onload = function () {
      resolve();
      this.remove();
    };
    script.onerror = reject;
    document.documentElement.appendChild(script);
  });
}

(async () => {
  try {
    await injectScript('lib/abc.js');
    await injectScript('lib/defpayload.js');
    await injectScript('lib/payload.js');
    await injectScript('lib/notpayload.js');
    await injectScript('lib/replayer.js');

    console.log('All scripts loaded.');
    
  } catch (err) {
    console.error('Error fetching or injecting scripts:', err);
    alert(`Failed to load scripts: ${err.message}`);
  }
})();

