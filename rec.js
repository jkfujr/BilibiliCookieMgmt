// 多直播流筛选
const apiList = [
    // local
    'https://api.live.bilibili.com',
    // TXC
    'http://100.100.201.51:63000',
    // ALI
    'http://100.100.201.61:63000',
    // DMIT-LB-ALL
    'http://100.100.201.71:65301',
];
// 匹配正则
const flv_regex = [
    /^https?\:\/\/[^\/]*cn-gotcha04\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*cn-gotcha04b\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*cn-gotcha07\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*cn-gotcha07b\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*cn-gotcha09\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*cn-gotcha09b\.bilivideo\.com/,
    /^https?\:\/\/[^\/]*ov-gotcha05\.bilivideo\.com/
];
// cookie
let cookie = '';
// HTTP 请求错误尝试次数
const httpErrorRepeat = 3;

const bilibiliCookieMgmt = {
    enable: true, // 是否启用cookie管理
    api_url: 'http://10.0.0.101:18000', // cookie管理API地址
    token: '1145141919810', // cookie管理API token
}

recorderEvents.onFetchStreamUrl = ({ roomid, qn }) => {
    try {
        cookie = new BilibiliCookieMgmt(bilibiliCookieMgmt).cookies;
    } catch (e) {
        console.error('cookie管理出错：' + e.toString());
    }

    const getDatas = [];

    for (const apiUrl of apiList) {
        try {
            getDatas.push(...v1_response(roomid, apiUrl));
        } catch (error) {
            console.error(error.toString());
        }
    }

    if (!getDatas.length)
        return null;

    const filter_urls = v1_urlFilter(getDatas);

    if (!filter_urls.length)
        return null;

    const random_url = filter_urls[0];

    return random_url;
}

const v1_response = (roomid, api_url) => {
    const playUrl = httpReq({
        url: `${api_url}/room/v1/Room/playUrl?cid=${roomid}&qn=10000&platform=web`,
        method: 'GET',
        headers: {
            'Origin': 'https://live.bilibili.com',
            'Referer': 'https://live.bilibili.com/',
            'Cookie': cookie ?? '',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36'
        },
    }, httpErrorRepeat);

    if (!playUrl.ok)
        throw new Error(`使用地址（${api_url}）获取直播流地址失败，status: ${playUrl.status}`);

    const body = JSON.parse(playUrl?.body);

    if (body?.code !== 0)
        throw new Error(`使用地址（${api_url}）获取直播流地址失败，${body?.message}`);

    /** @type {{"url": string}[]} */
    const durls = body?.data?.durl;

    return durls
}

const v1_urlFilter = stream_url => {
    const url_arr = [];

    for (const regexp of flv_regex) {
        for (const url of stream_url)
            if (regexp.test(url?.url)) {
                url_arr.push(url.url);
            }
    }

    return url_arr;
}

const httpReq = (res, repeatNum = 1) => {
    for (let index = 0; index <= repeatNum; index++) {
        if (index >= repeatNum)
            throw new Error("HTTP 错误请求次数超过阈值");
        try {
            return fetchSync(res.url, res);
        }
        catch (e) {
            console.error(e?.message + e?.stack);
        }
    }
    throw new Error("HTTP 请求失败");
};

const queryConvert_toStr = (inout) => Object
    .keys(inout)
    .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(inout[key])}`)
    .join('&');

class BilibiliCookieMgmt {
    message = '0';
    enable = false;

    token = '';
    cookies = '';

    #api_url = '';

    #api_headers = {
        'accept': 'application/json, text/plain, */*',
        'token': '',
    }

    #api_path_cookie_random = '/api/cookie/random';

    constructor(params) {
        this.#check_api_url(params?.api_url);
        this.#check_api_token(params?.token);

        this.enable = params?.enable ?? false;
        this.#api_url = params.api_url;
        this.#api_headers.token = this.token = params.token;

        if (this.enable)
            this.#run();
        else
            this.cookies = cookie;
    }

    #run() {
        try {
            this.#get_random_cookie();
        } catch (e) {
            console.warn('Cookie管理API请求失败，使用默认cookie：' + e.toString());
            this.cookies = cookie;
        }
    }

    #get_random_cookie() {
        const response = httpReq({
            url: `${this.#api_url}${this.#api_path_cookie_random}?type=sim`,
            method: 'GET',
            headers: this.#api_headers
        }, httpErrorRepeat);

        if (!response.ok)
            throw new Error(`获取随机cookie失败，status: ${response.status}, message: ${String(response.body)}`);

        const body = JSON.parse(response.body);
        this.#check_random_cookie_response(body);

        this.cookies = body.cookie;
    }

    #check_random_cookie_response(data) {
        if (data?.code !== 0)
            throw new Error(`获取随机cookie失败，${data?.message || data?.detail}`);

        if (typeof data?.cookie !== 'string')
            throw new TypeError(`cookie 字段必须是字符串，当前类型为${typeof data?.cookie}`);
    }

    #check_api_url(api_url) {
        if (!api_url)
            throw new TypeError('api_url不能为空');

        const urlObj = new URL(api_url);
        if (urlObj.protocol !== 'http:' && urlObj.protocol !== 'https:')
            throw new TypeError('api_url必须是http或https协议');
    }

    #check_api_token(token) {
        if (!token)
            throw new Error('token 不能为空');
    }
}