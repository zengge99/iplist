#!/bin/bash

SCRAPER_URL="https://xiaoyahelper.zngle.cf/scrap_tvbox.sh"

urldecode() {
    local input
    if [ $# -eq 0 ]; then
        input=$(cat)
    else
        input="$1"
    fi
    printf '%b' "${input//%/\\x}"
}

pulltgupdate() {
    CHANNEL="xiaoya_media"
    BASE_URL="https://t.me/s/$CHANNEL"
    current_url="$BASE_URL"

    for ((page=1; page<=10; page++)); do
        if [ $page != 1 ]; then
            before_param=$(echo "$page_content" | grep -oP '<link rel="prev" href="[^"]*before=\K[^"]+')
            [ -z "$before_param" ] && { echo "无法获取翻页参数，终止爬取"; break; }
            current_url="$BASE_URL?before=$before_param"
        else
            current_url="$BASE_URL"
        fi

        echo -e "\n====== 第${page}页 ======" >&2
        page_content=$(curl -s "$current_url")
        
        paste -d "#" \
        <(echo "$page_content" | grep -oP '<a [^>]*rel="noopener"[^>]*>\K[^<]+' | grep "xiaoya\.host" | sed 's|http://xiaoya.host:5678/|./|g') \
        <(echo "$page_content" | grep -oP '<div class="tgme_widget_message_text[^>]*>\K[^<]+') | awk -F'#' 'length($2) > 20 {print $1} length($2) <= 20 {print $0}' | urldecode
        echo

        sleep 1 
    done
}

rm -rf index 2>/dev/null
mkdir index 2>/dev/null
cd index
rm -rf tmp 2>/dev/null

wget https://raw.githubusercontent.com/xiaoyaDev/data/main/index.zip
unzip index.zip

mkdir tmp 2>/dev/null
cd tmp
pulltgupdate | sed '/^[ ]*$/d' > tg.txt

awk -F'#' '{
    if(FNR == NR) {
        data[$1] = $0;
    } else {
        if(!data[$1]){
            print $0;
        }
    }
}' ../index.video.txt tg.txt > delta.txt

cat delta.txt > ../index.video.txt
cat delta.txt > ../index.daily.txt

curl "$SCRAPER_URL" > scraper.sh
chmod 777 scraper.sh
./scraper.sh delta.txt --basic -n 3
mv -f output/delta.txt ./
./scraper.sh delta.txt -n 3
mv -f output/delta.txt ./

curl https://www2.bing.com

for file in ../*.txt; do
    echo "正在更新文件：$file"
    awk -F'#' '{
                if(FNR == NR) {
                    if (!($1 in data) || (NF > split(data[$1], arr, FS))) {
                        data[$1] = $0;
                    }
                } else {
                    if(data[$1] && (NF <= split(data[$1], arr, FS))){
                        print data[$1];
                    } else {
                        print $0;
                    }
                }
            }' delta.txt "$file" > "$file.tmp"
    mv -f "$file.tmp" "$file"
done

cd ..
rm -rf tmp

zip -rX ../text_files.zip *.txt

cd ..
rm -rf index
