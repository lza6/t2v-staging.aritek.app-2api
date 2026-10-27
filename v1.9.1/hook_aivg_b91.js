// AIVG b91 hook v4 — 反射 dump Request 对象（混淆类名安全）
Java.perform(function () {
    console.log("[*] hook v4 start");
    var HI = Java.use("ai.video.generator.text.video.apiservice.HeaderInterceptor");
    HI.intercept.overload('Sb.x').implementation = function (chain) {
        try {
            var req = chain.request();
            console.log("=== REQ toString: " + req.toString());
            var cls = req.getClass();
            console.log("    class=" + cls.getName());
            var ms = cls.getMethods();
            for (var i = 0; i < ms.length; i++) {
                var n = ms[i].getName();
                if (n === 'url' || n === 'method' || n === 'headers') console.log("    has method: " + n);
            }
            try { console.log("    url=" + req.url().toString()); } catch (e) {}
            try {
                var h = req.headers();
                for (var j = 0; j < h.size(); j++) console.log("    H " + h.name(j) + ": " + h.value(j));
            } catch (e) { console.log("    headers err " + e); }
        } catch (e) { console.log("[dump err] " + e); }
        return this.intercept(chain);
    };
    console.log("[+] hooked");
});
