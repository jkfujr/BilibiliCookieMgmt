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
    enable: false, // 是否启用cookie管理
    api_url: 'http://127.0.0.1:18000', // cookie管理API地址
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
    cookie_list = [];
    cookies = '';

    #api_url = '';

    #api_headers = {
        'accept': 'application/json, text/plain, */*',
        'token': '',
    }

    #api_path_cookie_get = '/api/cookie';

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
        this.#get_cookies_list();

        if (!this.cookie_list.length) {
            console.warn('cookie列表为空，无法获取有效cookie');
            console.debug(JSON.stringify(this.cookie_list));
            return;
        }

        const cookie_list = this.cookie_list[
            Math.floor(Math.random() * this.cookie_list.length)
        ];

        this.#get_cookies(cookie_list);
    }

    #get_cookies_list() {
        const cookie_list = httpReq({
            url: `${this.#api_url}${this.#api_path_cookie_get}`,
            method: 'GET',
            headers: this.#api_headers
        }, httpErrorRepeat);

        if (!cookie_list.ok)
            throw new Error(`获取cookie列表失败，status: ${cookie_list.status}, message: ${String(cookie_list.body)}`);

        const body = JSON.parse(cookie_list.body);
        this.#check_cookie_list(body);

        this.cookie_list = body.filter(cookie => cookie.cookie_valid);
    }

    #get_cookies({ DedeUserID }) {
        const data = httpReq({
            url: `${this.#api_url}${this.#api_path_cookie_get}?${queryConvert_toStr({ DedeUserID })}`,
            method: 'GET',
            headers: this.#api_headers
        }, httpErrorRepeat);

        if (!data?.ok)
            throw new Error(`获取cookie失败，status: ${data.status}, message: ${String(data.body)}`);

        const body = JSON.parse(data.body);
        this.#check_cookies_data(body);

        this.cookies = body.cookie_info.cookies.map(cookie => `${cookie.name}=${cookie.value}`).join('; ');
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

    #check_cookie_list(data) {
        if (!Array.isArray(data))
            throw new TypeError('data 必须是数组');

        for (const cookie of data) {
            if (typeof cookie?.DedeUserID !== 'string')
                throw new TypeError(`data.DedeUserID 字段必须是字符串，当前类型为${typeof cookie?.DedeUserID}`);

            if (typeof cookie?.cookie_valid !== 'boolean')
                throw new TypeError(`data.cookie_valid 字段必须是布尔值，当前类型为${typeof cookie?.cookie_valid}`);
        }
    }

    #check_cookies_data(data) {
        if (data?.code !== 0 && !data?.cookie_info)
            throw new Error(`获取cookie失败，${data?.message || data?.detail}`);

        if (!Array.isArray(data?.cookie_info?.cookies))
            throw new TypeError('data.cookie_info.cookies 必须是数组');

        for (const cookie of data.cookie_info.cookies) {
            if (typeof cookie?.name !== 'string')
                throw new TypeError(`cookie.name 字段必须是字符串，当前类型为${typeof cookie?.name}`);

            if (typeof cookie?.value !== 'string')
                throw new TypeError(`cookie.value 字段必须是字符串，当前类型为${typeof cookie?.value}`);
        }
    }
}