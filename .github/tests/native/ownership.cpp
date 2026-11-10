#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

namespace {
typedef std::basic_string<PA_Unichar> Text;
std::map<PA_Unichar*, Text> strings;
std::map<PA_Handle, size_t> handles;
std::map<PA_Picture, int> pictures;
bool nullEmpty = false;
bool failHandle = false;
bool failCommand = false;
Text expected;

void check(bool condition, const char* message)
{
    if (!condition) throw std::runtime_error(message);
}

Text text(const char* utf8)
{
    CFStringRef s = CFStringCreateWithCString(NULL, utf8, kCFStringEncodingUTF8);
    check(s != NULL, "invalid synthetic fixture");
    Text result(CFStringGetLength(s), 0);
    if (!result.empty())
        CFStringGetCharacters(s, CFRangeMake(0, result.size()), &result[0]);
    CFRelease(s);
    return result;
}

PA_Unistring makeString(const PA_Unichar* p)
{
    PA_Unistring result = {};
    Text value = p ? Text(p) : Text();
    result.fLength = value.size();
    if (!value.empty() || !nullEmpty) {
        result.fString = new PA_Unichar[value.size() + 1];
        std::copy(value.begin(), value.end(), result.fString);
        result.fString[value.size()] = 0;
        PA_Unichar* allocation = result.fString;
        strings[allocation] = value;
    }
    return result;
}

Text readString(PA_Unistring s)
{
    if (!s.fString) {
        check(s.fLength == 0, "null string with nonzero length");
        return Text();
    }
    PA_Unichar* allocation = s.fString;
    check(strings.count(allocation) == 1, "read of disposed string");
    check(strings.at(allocation).size() == static_cast<size_t>(s.fLength),
          "string length mismatch");
    check(s.fString[s.fLength] == 0, "missing UTF-16 terminator");
    return Text(s.fString, s.fLength);
}

void disposeString(PA_Unistring s)
{
    if (s.fString) {
        PA_Unichar* allocation = s.fString;
        check(strings.erase(allocation) == 1, "double disposal of path string");
        delete[] s.fString;
    }
}

PA_Picture makePicture()
{
    PA_Picture p = new char;
    pictures[p] = 1;
    return p;
}

void disposePicture(PA_Picture p)
{
    if (!p) return;
    check(pictures.count(p) == 1, "disposal of unowned picture");
    if (--pictures[p] == 0) {
        pictures.erase(p);
        delete static_cast<char*>(p);
    }
}

void clear(PA_Variable* v)
{
    // Raw kind 0 is an SDK command-handle-failure sentinel, not a string.
    check(v->fType != 0, "cleared invalid command failure sentinel");
    switch (v->fType) {
        case eVK_Unistring: disposeString(v->uValue.fString); break;
        case eVK_Picture: disposePicture(v->uValue.fPicture); break;
        case eVK_ArrayUnicode:
            for (int i = 0; i <= v->uValue.fArray.fNbElements; ++i)
                disposeString((*reinterpret_cast<PA_Unistring**>(v->uValue.fArray.fData))[i]);
            PA_DisposeHandle(v->uValue.fArray.fData);
            break;
        case eVK_ArrayLongint: PA_DisposeHandle(v->uValue.fArray.fData); break;
        case eVK_Undefined: case eVK_Longint: break;
        default: throw std::runtime_error("unimplemented clear kind");
    }
    *v = {};
    v->fType = eVK_Undefined;
}

void callback(short selector, EngineBlock* eb)
{
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            break;
        case EX_DISPOSE_UNISTRING: disposeString(eb->fUniString1); break;
        case EX_SET_UNISTRING: {
            PA_Unistring replacement = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            disposeString(eb->fUniString1);
            eb->fUniString1 = replacement;
            break;
        }
        case EX_CREATE_PICTURE: eb->fPicture = makePicture(); eb->fError = 0; break;
        case EX_DISPOSE_PICTURE: disposePicture(eb->fPicture); break;
        case EX_DUPLICATE_PICTURE:
            if (eb->fPicture) {
                PA_Picture picture = eb->fPicture;
                check(pictures.count(picture) == 1, "retain of dead picture");
                if (eb->fParam1 == 0) ++pictures[picture];
                else eb->fPicture = makePicture();
            }
            break;
        case EX_GET_PICTURE_DATA:
            // No representations. Failed output is deliberately unspecified;
            // callers must check the SDK error before inspecting it.
            eb->fError = eER_IncompatibleTypes;
            break;
        case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable*>(eb->fPtr1)); break;
        case EX_HANDLE_MANAGER: {
            PA_Handle h = eb->fHandle;
            eb->fError = 0;
            switch (eb->fParam1) {
                case 1:
                    if (failHandle) {
                        eb->fHandle = NULL;
                        eb->fError = eER_IncompatibleTypes;
                        break;
                    }
                    h = new char*;
                    *h = static_cast<char*>(std::calloc(1, std::max<sLONG_PTR>(1, +eb->fParam2)));
                    check(*h != NULL, "test handle allocation failed");
                    handles[h] = eb->fParam2;
                    eb->fHandle = h;
                    break;
                case 2:
                    check(handles.erase(h) == 1, "handle double disposal");
                    std::free(*h);
                    delete h;
                    break;
                case 3: {
                    check(handles.count(h) == 1, "resize invalid handle");
                    void* resized = std::realloc(*h, std::max<sLONG_PTR>(1, +eb->fParam2));
                    check(resized != NULL, "test handle resize failed");
                    *h = static_cast<char*>(resized);
                    handles[h] = eb->fParam2;
                    break;
                }
                case 4: eb->fParam2 = handles.at(h); break;
                case 5: eb->fParam3 = reinterpret_cast<sLONG_PTR>(*h); break;
                case 6: break;
                default: throw std::runtime_error("unimplemented handle operation");
            }
            break;
        }
        case EX_CONVERT_CHARSET_TO_CHARSET: {
            check(eb->fParam2 == eVTC_UTF_8 && eb->fParam4 == eVTC_UTF_16,
                  "unexpected charset conversion");
            CFStringRef s = CFStringCreateWithBytes(NULL, static_cast<UInt8*>(eb->fPtr1),
                                                    eb->fParam1, kCFStringEncodingUTF8, false);
            check(s != NULL, "invalid conversion fixture");
            CFIndex units = CFStringGetLength(s);
            check(eb->fParam3 >= units * static_cast<int>(sizeof(PA_Unichar)),
                  "UTF-16 capacity is in bytes");
            // Return bytes written, excluding a terminator. Do not initialize
            // unused capacity or make the engine return code units.
            CFStringGetCharacters(s, CFRangeMake(0, units), static_cast<UniChar*>(eb->fPtr2));
            eb->fParam3 = units * sizeof(PA_Unichar);
            eb->fError = 0;
            CFRelease(s);
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            PA_Variable** args = static_cast<PA_Variable**>(eb->fPtr1);
            PA_Variable* returned = static_cast<PA_Variable*>(eb->fPtr2);
            check(returned->fType == eVK_Undefined, "command result not initialized");
            eb->fError = 0;
            if (failCommand) {
                eb->fError = eER_IncompatibleTypes;
                break;
            }
            switch (eb->fParam1) {
                case 678:
                    check(readString(args[0]->uValue.fString) == expected, "path content mismatch");
                    clear(args[1]);
                    PA_SetPictureVariable(args[1], makePicture());
                    break;
                case 1002:
                    check(readString(args[1]->uValue.fString) == expected,
                          "conversion format content mismatch");
                    check(pictures.count(static_cast<PA_Picture>(args[0]->uValue.fPicture)) == 1, "copy input dead");
                    break;
                case 988: check(pictures.count(static_cast<PA_Picture>(args[0]->uValue.fPicture)) == 1, "gray input dead"); break;
                case 457:
                    check(pictures.count(static_cast<PA_Picture>(args[0]->uValue.fPicture)) == 1, "size input dead");
                    PA_SetLongintVariable(args[1], 17);
                    PA_SetLongintVariable(args[2], 23);
                    break;
                case 679:
                    check(pictures.count(static_cast<PA_Picture>(args[0]->uValue.fPicture)) == 1, "thumbnail input dead");
                    clear(args[1]);
                    PA_SetPictureVariable(args[1], makePicture());
                    break;
                default: throw std::runtime_error("unexpected 4D command");
            }
            break;
        }
        default: throw std::runtime_error("unimplemented engine selector");
    }
}

void balanced()
{
    check(strings.empty(), "leaked string owners (including allocated empties)");
    check(handles.empty(), "leaked SDK handles");
    check(pictures.empty(), "leaked picture references (including overwritten empties)");
}

const char* fixtures[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC", "\xF0\x9F\x98\x80", ""};

void filePath()
{
    for (const char* fixture : fixtures) {
        expected = text(fixture);
        {
            CPicture p;
            CUTF8String path(reinterpret_cast<const uint8_t*>(fixture));
            p.fromFileAtPath(&path);
            check(pictures.at(p.getPicture()) == 1, "file output owner not released after retain");
            unsigned int width = 0, height = 0;
            p.getSize(&width, &height);
            check(width == 17 && height == 23, "retained picture did not survive argument clear");
        }
        balanced();
    }
}

void bytes()
{
    {
        CPicture p;
        const uint8_t data[] = {1, 2, 3};
        for (int i = 0; i != 3; ++i) {
            p.setBytes(data, sizeof(data));
            check(pictures.at(p.getPicture()) == 1, "setBytes temporary retained owner leaked");
        }
        p.setBytes(NULL, 0);
    }
    balanced();
}

void copy()
{
    for (const char* fixture : fixtures) {
        expected = text(fixture);
        PA_Picture result;
        {
            CPicture p;
            result = p.createCopy(fixture);
        }
        check(pictures.count(result) == 1 && pictures.at(result) == 1,
              "returned picture handoff lost or retained extra owners");
        PA_DisposePicture(result);
        balanced();
    }
}

void formats()
{
    C_PICTURE p;
    expected = text(".png");
    PA_DisposePicture(p.createCopyPNG());
    expected = text(".jpg");
    PA_DisposePicture(p.createCopyJPG());
    expected = text(".tif");
    PA_DisposePicture(p.createCopyTIF());
}

void emptyFile()
{
    expected = Text();
    {
        CPicture p;
        CUTF8String path;
        p.fromFileAtPath(&path);
        check(pictures.at(p.getPicture()) == 1, "file output owner not released after retain");
    }
    balanced();
}

void pictureArguments()
{
    {
        CPicture p;
        PA_Picture result = p.createGrayScale();
        PA_DisposePicture(result);
        unsigned int width, height;
        p.getSize(&width, &height);
        check(width == 17 && height == 23, "size output mismatch");
        result = p.createThumbnail(17, 23);
        PA_DisposePicture(result);
        PA_Picture incoming = PA_CreatePicture(NULL, 0);
        BytePtr params[] = {reinterpret_cast<BytePtr>(&incoming)};
        p.fromParamAtIndex(params, 1);
        PA_DisposePicture(incoming);
        PA_Picture output = PA_CreatePicture(NULL, 0);
        params[0] = reinterpret_cast<BytePtr>(&output);
        p.toParamAtIndex(params, 1);
        PA_DisposePicture(output);
        output = NULL;
        p.toParamAtIndex(params, 1);
        PA_DisposePicture(output);
        sLONG_PTR returned = 0;
        p.setReturn(&returned);
        PA_DisposePicture(reinterpret_cast<PA_Picture>(returned));
    }
    balanced();
}

void arrays()
{
    for (int repeat = 0; repeat != 3; ++repeat) {
        PA_Variable destination = PA_CreateVariable(eVK_ArrayUnicode);
        BytePtr params[] = {reinterpret_cast<BytePtr>(&destination)};
        {
            ARRAY_TEXT a;
            a.setSize(1);
            for (const char* fixture : fixtures) {
                Text value = text(fixture);
                a.appendUTF16String(value.c_str(), value.size());
            }
            a.toParamAtIndex(params, 1);
            ARRAY_TEXT independent;
            independent.fromParamAtIndex(params, 1);
            for (int i = 1; i <= 4; ++i)
                check(readString(PA_GetStringInArray(destination, i)) == text(fixtures[i - 1]),
                      "array output content mismatch");
            // A borrowed getter is copied before its owner is mutated.
            PA_Unistring borrowed = PA_GetStringInArray(destination, 1);
            C_TEXT scalar;
            scalar.setUTF16String(&borrowed);
            PA_Unistring owned = PA_CreateUnistring(const_cast<PA_Unichar*>(text("replace").c_str()));
            PA_SetStringInArray(destination, 1, &owned);
            check(Text(scalar.getUTF16StringPtr(), scalar.getUTF16Length()) == text("ASCII"),
                  "borrowed scalar copy did not survive replacement");
            a.toParamAtIndex(params, 1);
            PA_ResizeArray(&destination, 0);
            independent.toParamAtIndex(params, 1);
            for (int i = 1; i <= 4; ++i)
                check(readString(PA_GetStringInArray(destination, i)) == text(fixtures[i - 1]),
                      "independent copied owner did not survive shrink");
            PA_Unistring first = PA_GetStringInArray(destination, 1);
            PA_Unistring second = PA_GetStringInArray(destination, 2);
            check(first.fString != second.fString, "array outputs share an owner");
        }
        PA_ClearVariable(&destination);
        balanced();
    }
    PA_Variable destination = PA_CreateVariable(eVK_Undefined);
    BytePtr params[] = {reinterpret_cast<BytePtr>(&destination)};
    ARRAY_TEXT a;
    a.setSize(1);
    a.toParamAtIndex(params, 1);
    PA_ClearVariable(&destination);
    balanced();
}

void rejections()
{
    PA_Variable a = PA_CreateVariable(eVK_ArrayUnicode);
    PA_Unistring input = PA_CreateUnistring(const_cast<PA_Unichar*>(text("caller").c_str()));
    PA_Unichar* allocation = input.fString;
    PA_SetStringInArray(a, -1, &input);
    PA_SetStringInArray(a, 1, &input);
    PA_Variable wrong = PA_CreateVariable(eVK_Longint);
    PA_SetStringInArray(wrong, 0, &input);
    PA_Variable noData = {};
    noData.fType = eVK_ArrayUnicode;
    PA_SetStringInArray(noData, 0, &input);
    PA_SetStringInArray(a, 0, NULL);
    check(input.fString == allocation && readString(input) == text("caller"),
          "rejection consumed caller-owned string");
    PA_DisposeUnistring(&input);
    PA_ClearVariable(&a);
    failHandle = true;
    PA_Variable failed = PA_ExecuteCommandByID(678, NULL, 0);
    failHandle = false;
    check(failed.fType == 0, "SDK failure sentinel changed");
    balanced();
}

void scalarContent()
{
    for (const char* fixture : fixtures) {
        expected = text(fixture);
        PA_Unistring input = PA_CreateUnistring(const_cast<PA_Unichar*>(expected.c_str()));
        PA_Variable owner = PA_CreateVariable(eVK_Undefined);
        PA_SetStringVariable(&owner, &input);
        check(owner.uValue.fString.fString == input.fString, "scalar setter is not shallow");
        C_TEXT independent;
        independent.setUTF16String(&owner.uValue.fString);
        PA_ClearVariable(&owner);
        check(Text(independent.getUTF16StringPtr(), independent.getUTF16Length()) == expected,
              "scalar copied string lost with owner");
        PA_Unistring output = PA_CreateUnistring(NULL);
        BytePtr params[] = {reinterpret_cast<BytePtr>(&output)};
        independent.toParamAtIndex(params, 1);
        check(readString(output) == expected, "content setter mismatch");
        PA_PluginParameters resultParams;
        PluginBlock block = {};
        PA_Unistring* result = &output;
        block.fResult = &result;
        resultParams = &block;
        PA_ReturnString(resultParams, const_cast<PA_Unichar*>(expected.c_str()));
        check(readString(output) == expected, "PA_ReturnString content setter mismatch");
        PA_DisposeUnistring(&output);
        balanced();
    }
}

void procedureFailure()
{
    for (int mode = 0; mode != 2; ++mode) {
        {
            CPicture p;
            failHandle = mode == 0;
            failCommand = mode == 1;
            CUTF8String path(reinterpret_cast<const uint8_t*>("synthetic.png"));
            p.fromFileAtPath(&path);
            PA_DisposePicture(p.createCopy(".png"));
            PA_DisposePicture(p.createGrayScale());
            PA_DisposePicture(p.createThumbnail(17, 23));
            unsigned int width = 17, height = 23;
            p.getSize(&width, &height);
            check(width == 0 && height == 0, "failed command modified scalar outputs");
            failHandle = false;
            failCommand = false;
        }
        balanced();
    }
}

void dispatch()
{
    PA_Variable names = PA_CreateVariable(eVK_ArrayUnicode);
    PA_Variable values = PA_CreateVariable(eVK_ArrayLongint);
    PA_long32 screen = 1;
    BytePtr params[] = {reinterpret_cast<BytePtr>(&names), reinterpret_cast<BytePtr>(&values),
                        reinterpret_cast<BytePtr>(&screen)};
    PA_long32 result = -1;
    // macOS has no Windows metrics implementation: both arrays stay empty.
    FourDPackex(1, params, NULL, &result);
    check(PA_GetArrayNbElements(names) == 0 && PA_GetArrayNbElements(values) == 0,
          "macOS dispatcher output changed");
    PA_ClearVariable(&names);
    PA_ClearVariable(&values);
    params[0] = reinterpret_cast<BytePtr>(&screen);
    params[1] = reinterpret_cast<BytePtr>(&screen);
    FourDPackex(2, params, NULL, &result);
    check(result == 0, "scalar command return changed");
    FourDPackex(3, params, NULL, &result);
    balanced();
}
}

int main(int argc, char** argv)
{
    try {
        check(argc >= 2, "missing scenario");
        nullEmpty = argc > 2 && std::string(argv[2]) == "null-empty";
        gCall4D = callback;
        std::string name(argv[1]);
        if (name == "file-path") filePath();
        else if (name == "set-bytes") bytes();
        else if (name == "copy-utf16") copy();
        else if (name == "copy-formats") formats();
        else if (name == "file-empty") emptyFile();
        else if (name == "picture-arguments") pictureArguments();
        else if (name == "arrays") arrays();
        else if (name == "rejections") rejections();
        else if (name == "scalar-content") scalarContent();
        else if (name == "dispatcher") dispatch();
        else if (name == "procedure-failure") procedureFailure();
        else throw std::runtime_error("unknown scenario");
        balanced();
        std::cout << name << ": PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << argv[1] << ": FAIL: " << e.what() << '\n';
        return 1;
    }
}
