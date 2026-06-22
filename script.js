document.addEventListener("DOMContentLoaded", () => {
    const pngSeq = document.getElementById('png-sequence');
    const vid2 = document.getElementById('video-part2');
    const vid3 = document.getElementById('video-part3');
    const btnContainer = document.getElementById('button-container');

    // Configuration for PNG sequence
    const totalPngs = 12;
    const fps = 24; // You can adjust this for faster/slower PNG sequence
    const frameDuration = 1000 / fps;

    // Preload PNGs
    const pngImages = [];
    for(let i=0; i<totalPngs; i++) {
        const img = new Image();
        const num = i.toString().padStart(2, '0');
        img.src = `png/pngseq${num}.png`;
        pngImages.push(img);
    }

    let currentFrame = 0;

    function playPngSequence() {
        pngSeq.style.opacity = 1;
        // Pre-set the first frame
        pngSeq.src = pngImages[0].src;
        
        const interval = setInterval(() => {
            currentFrame++;
            if(currentFrame >= totalPngs) {
                clearInterval(interval);
                pngSeq.style.opacity = 0;
                playPart2();
                return;
            }
            pngSeq.src = pngImages[currentFrame].src;
        }, frameDuration);
    }

    function playPart2() {
        vid2.style.opacity = 1;
        vid2.play();
        vid2.onended = () => {
            vid2.style.opacity = 0;
            playPart3();
        };
    }

    function playPart3() {
        vid3.style.opacity = 1;
        vid3.play();
        
        // Fade in buttons gracefully after part 3 starts playing
        setTimeout(() => {
            btnContainer.style.opacity = 1;
            btnContainer.style.pointerEvents = 'auto';
        }, 300);
    }

    // Handle button hovers to change images
    document.querySelectorAll('.power-btn img').forEach(img => {
        // Preload hover image
        const hoverImg = new Image();
        hoverImg.src = img.getAttribute('data-hover');

        img.addEventListener('mouseenter', function() {
            this.src = this.getAttribute('data-hover');
        });
        img.addEventListener('mouseleave', function() {
            this.src = this.getAttribute('data-normal');
        });
    });

    // Dummy click handlers for power actions
    // You will need to hook these up to your local environment
    // e.g., using window.chrome.webview, child_process in Electron, or custom protocol
    document.getElementById('btn-logout').addEventListener('click', () => {
        console.log("Logout triggered");
        // Example if using a custom protocol like yasb://logout
        // window.location.href = "yasb://command/logout";
    });

    document.getElementById('btn-restart').addEventListener('click', () => {
        console.log("Restart triggered");
    });

    document.getElementById('btn-shutdown').addEventListener('click', () => {
        console.log("Shutdown triggered");
    });

    // Start the animation sequence
    playPngSequence();
});
